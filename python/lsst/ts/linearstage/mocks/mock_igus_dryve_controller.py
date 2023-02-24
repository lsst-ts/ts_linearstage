# This file is part of ts_LinearStage.
#
# Developed for Vera Rubin Observatory Telescope and Site Systems
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License

__all__ = ["MockIgusDryveController"]

import asyncio

from ..controllers.igus_dryve.telegrams import (
    telegrams_read,
    telegrams_read_errs,
    telegrams_write,
)
from ..controllers.igus_dryve.utils import derive_handshake, read_telegram

_STD_TIMEOUT = 5  # seconds


class MockIgusDryveController:
    """Mock Igus Dryve v1 controller that talks over TCP/IP.

    Parameters
    ----------
    port : int
        TCP/IP port. If 0 then pick an available port.

    Notes
    -----
    To start the server:

        ctrl = MockIgusDryveController(...)
        await ctrl.start()

    To stop the server:

        await ctrl.stop()

    Known Limitations:

    * Nothing works yet
    """

    def __init__(self, port, host, log):
        # If port == 0 then this will be updated to the actual port
        # in `start`, right after the TCP/IP server is created.
        self.port = port
        self.host = host

        self.log = log.getChild("MockIgusDryveController")
        self.server = None

        # Possible incoming/outgoing telegrams
        # Telegrams to be received by controller, which are identical to
        # what is written by the client (hardware.py)
        # must be tuples for them to be hashable
        self.telegram_incoming = telegrams_write
        # Telegrams to be send by controller, which are identical to
        # what is read by the client (hardware.py)
        self.telegram_responses = telegrams_read
        #
        self.telegram_responses_errs = telegrams_read_errs
        # defines current state of system, must be consistent with a name in
        self.state = "switch_on_disabled"
        self.status_bits0_7 = 64
        self.status_bits8_16 = 6
        self.feed_constant_mm_per_rot = None
        self.homing_speed_switch_rpm = None
        self.homing_speed_zero_rpm = None
        self.homing_accel_rpm_per_min2 = None
        self.motion_accel_rpm_per_min2 = None
        self.motion_accel_rpm = None
        # define operational mode ( undefined (0), homing (6) or
        # position profile (1))
        self.mode = 0
        # Current position is often near zero but not actually zero when
        # turned on
        self.current_pos = 1.2
        self.target_pos = 0.0

        # last received command
        self.cmd = None

        # Create the dictionary that defines the responses based on the
        # incoming telegram
        # Dict of command: (has_argument, function).
        # The function is called with:
        # * No arguments, if `has_argument` False.
        # * The argument as a string, if `has_argument` is True.
        # Note that the arguments of the dictionary must be hashable
        # This means using tuples instead of dictionaries

        # FIXME: remove the has-data bit boolean
        self.dispatch_dict = {
            self.telegram_incoming["status_request"]: (False, self.do_status_request),
            self.telegram_incoming["switch_on"]: (False, self.do_switch_on),
            self.telegram_incoming["enable_operation"]: (False, self.enable_operation),
            self.telegram_incoming["unexpected_response_check"]: (
                False,
                self.do_set_weird_state1,
            )
            # "MV": (True, self.do_set_cmd_az),
        }

        self.log.debug("Initialized MockIgusDryveController")

    async def start(self):
        """Start the TCP/IP server.

        Set start_task done and start the command loop.
        """
        self.server = await asyncio.start_server(
            self.cmd_loop, host=self.host, port=self.port
        )
        if self.port == 0:
            self.port = self.server.sockets[0].getsockname()[1]
            self.log.debug(
                f"Started TCP/IP Server on host {self.host} and port {self.port}"
            )
        return self.host, self.port

    async def stop(self, timeout=5):
        """Stop the TCP/IP server."""
        if self.server is None:
            return

        server = self.server
        self.server = None
        server.close()
        await asyncio.wait_for(server.wait_closed(), timeout=timeout)

    async def cmd_loop(self, reader, writer):
        """Execute commands and output replies."""
        self.log.info("cmd_loop begins")
        while True:
            line = await read_telegram(reader, timeout=_STD_TIMEOUT)
            self.log.debug(f"Simulated Controller received command: {line!r}")
            if not line:
                # connection lost; close the writer and exit the loop
                writer.close()
                return
            if line:
                try:
                    items = len(line)
                    # FIXME - remove _cmd and replace with self.cmd
                    _cmd = tuple(line)
                    self.cmd = tuple(line)
                    # check if command is in dictionary
                    if _cmd not in self.dispatch_dict:
                        # Check if we can interpret the command
                        outputs = self.interpret_write_telegram(_cmd)
                        has_data = False
                        if outputs is None:
                            import pdb

                            pdb.set_trace()
                            raise KeyError(f"Unsupported command {_cmd}")
                    else:
                        has_data, func = self.dispatch_dict[_cmd]

                        # Has_data is going to be deprecated, but hasn't yet
                        if has_data:
                            outputs = func(items[0])
                        else:
                            outputs = func()

                    if outputs:
                        self.log.debug(
                            f"Simulated Controller will publish {len(outputs)} telegrams"
                        )
                        count = 1
                        for output in outputs:
                            self.log.debug(
                                "Simulated Controller responding with "
                                f"telegram {count} of {len(outputs)} with: {output}"
                            )
                            writer.write(bytearray(output))
                            await writer.drain()
                            await asyncio.sleep(0.2)
                            count += 1
                except Exception:
                    self.log.exception(f"command {line} failed")

    def do_status_request(self):
        self.log.debug(
            f"Publishing status requested from status_request command, corresponding to state {self.state}"
        )
        self.log.debug(f"Responding with {self.telegram_responses[self.state]}")
        return [self.telegram_responses[self.state]]

    def do_shutdown(self):
        """Transitions state from to switch_on_disabled to ready_to_switch_on
        and publishes handshake.
        Transitions can occur from multiple states.
        This sets

        Returns
        -------
        response_telegrams : `list`
            List of telegrams to send in response

        """
        if self.state in [
            "switch_on_disabled",
            "ready_to_switch_on",
            "switched_on",
            "operation_enabled",
        ]:
            # can now return a handshake
            _response_telegrams = [derive_handshake(self.cmd)]

            self.state = "ready_to_switch_on"
            # set bits 1 (enable voltage) and 6 (absolute positioning)
            self.status_bits0_7 = 0b100001  # 33
            self.status_bits8_16 = self.status_bits8_16 | 6
            return _response_telegrams
        else:
            raise KeyError(
                f"Current state of {self.state} does not have a keyword pair with appropriate response"
            )

    def do_switch_on(self):
        """Transitions state to from switch_on_disabled to switched_on and
         publishes handshake

        Returns
        -------
        response_telegrams : `list`
            List of telegrams to send in response

        """
        if self.state in [
            "switch_on_disabled",
            "ready_to_switch_on",
            "switched_on",
            "operation_enabled",
        ]:
            # can now return a handshake
            _response_telegrams = [derive_handshake(self.cmd)]
            self.state = "switched_on"
            return _response_telegrams
        else:
            raise KeyError(
                f"Current state of {self.state} does not have a keyword pair with appropriate response"
            )

    def do_set_weird_state1(self):
        """Transitions state to something the program isn't expecting just
        to test error handling

        Returns
        -------
        response_telegrams : `list`
            List of telegrams to send in response

        """

        # can now return a handshake and set the new state
        _response_telegrams = [derive_handshake(self.cmd)]
        self.state = "weird_state1"
        return _response_telegrams

    def enable_operation(self):
        """Transitions state from switched_on to operation_enabled and
        publishes handshake

        Returns
        -------
        response_telegrams : `list`
            List of telegrams to send in response
        """
        if self.state in ["switched_on", "operation_enabled", "target_reached"]:
            # can now return a handshake
            _response_telegrams = [derive_handshake(self.cmd)]
            self.state = "operation_enabled"
            return _response_telegrams
        else:
            raise KeyError(
                f"Current state of {self.state} does not have an appropriate response in mock."
            )

    def do_set_mode(self, mode):
        """Changes mode (based on received 6060h telegram)
        Modes which are supported by the are defined in
        interpret_write_telegram

        Parameters
        ----------

        mode : `int`
            Modes are homing (6), or profile position (1)
        """

        # 6 is homing, 1 is profile positioning, 0 is undefined
        # Code does not currently support other modes
        if mode == 6:
            self.log.debug("Mock Controller Setting mode = homing")
            self.mode = 6
        elif mode == 1:
            self.log.debug("Mock Controller Setting mode = profile positioning")
            self.mode = 1
        else:
            raise KeyError(f"Mode = {mode} is not supported by the mocked controller.")

        # Respond with handshake
        response_telegrams = [derive_handshake(self.cmd)]
        return response_telegrams

    def do_get_mode(self):
        """Retrieves current mode (based on received 6061h telegram)
        Modes which are supported by the are defined in
        interpret_write_telegram.

        """

        # 6 is homing, 1 is profile positioning, 0 is undefined
        # _response = [0, 0, 0, 0, 0, 14, 0, 43, 13,
        # 0, 0, 0, 96, 97, 0, 0, 0, 0, 1, self.mode]
        _response = list(self.cmd[0:19])
        _response[5] = 14
        _response.append(self.mode)

        response_telegrams = [_response]
        return response_telegrams

    async def move(self, final_state, interval=None):
        """Simulates a movement for X seconds, then changes state"""

        if self.mode == 1:  # Standard motion
            self.log.debug(f"Starting motion movement for {interval} seconds")
            # Switch state to moving
            self.state = "move_being_executed"
            # Determine how long it'll take to get there
            # Just assume constant velocity and ignore accelerations
            time_to_target = (
                self.target_pos - self.current_pos
            ) / self.motion_speed_mm_per_s
            self.log.debug(f"Estimated time to target is {time_to_target} seconds")
            _time = 0
            if interval is None:
                while _time < time_to_target:
                    self.current_pos = (
                        self.current_pos
                        + _time / time_to_target * self.motion_speed_mm_per_s
                    )
                    await asyncio.sleep(1)
                    _time += 1
                await asyncio.sleep(time_to_target)
            self.current_pos = self.target_pos

        elif self.mode == 6:  # homing
            self.state = "homing_being_executed"
            self.log.debug(f"Starting homing motion movement for {interval} seconds")
            await asyncio.sleep(interval)
            self.current_pos = 0.0

        self.log.debug(f"Movement completed, now changing state to {final_state}")
        self.state = final_state

    def do_start_movement(self):
        """Start motion for given mode (based on received 6040h telegram)"""

        # Not sure what happens yet when motion is happening.
        if self.mode == 6:
            # this is homing,
            # Respond immediately with handshake
            _response_telegrams = [
                derive_handshake(self.cmd),
            ]
            self.state = "homing_being_executed"
            # How to add a 3s delay here that changes the state later on?
            coro = asyncio.create_task(self.move("target_reached", interval=3))

        elif self.mode == 1:
            # This is moving between positions
            # Respond immediately with handshake
            _response_telegrams = [
                derive_handshake(self.cmd),
            ]
            # Send stage
            coro = asyncio.create_task(self.move("target_reached"))

        else:
            raise ValueError(f"Movement not supported in mode {self.mode}")

        asyncio.ensure_future(coro)

        return _response_telegrams

    def interpret_write_telegram(self, telegram):
        """Breaks down what a telegram means when sent to the controller. This
        is used primarily for the mock controller to identify which methods
        to run upon receiving the telegram."""

        # Controlword 6040h telegram
        # bits [12,13] == [60h,40h] (hex) == [96,64] in decimal
        if telegram[12] == 96 and telegram[13] == 64:
            self.log.debug("Interpreted 6040h (ControlWord) telegram")
            if telegram[19] == 31:
                # 31 means bits 1 through 5 are set
                # start movement
                return self.do_start_movement()
            if telegram[19] == 6:
                # means only enable voltage is set,
                # this is a shutdown signal
                return self.do_shutdown()

        # Modes of Operation (setmode) (6060h) telegram
        # bits [12,13] == [60h,60h] in hex or [96,96] in decimal
        if telegram[12] == 96 and telegram[13] == 96:
            # the desired mode is set in byte 19
            self.log.debug("Interpreted 6060h (Setmode) telegram")
            return self.do_set_mode(telegram[19])

        # Modes of Operation Display (getmode) (6061h) telegram
        # bits [12,13] == [60h,60h] in hex or [96,97] in decimal
        if telegram[12] == 96 and telegram[13] == 97:
            # the desired mode is set in byte 19
            self.log.debug("Interpreted 6061h (Getmode) telegram")
            return self.do_get_mode()

        # 6092h_01h Feed constant
        # 6092h_02h Shaft Revolutions for feed constant
        # Can be either trying to set feed rate (will have 1 on byte 14)
        # or the shaft revolutions per rate (will have 2 on byte 14)
        if telegram[12] == 96 and telegram[13] == 146:
            self.log.debug("Interpreted 6092h (Feed Constant) telegram")
            # Can be either trying to set the feedrate or shaft revolutions
            if telegram[14] == 1:
                # feed constant in mm/rotation comes from bytes 19 and 20
                # this reconstructs a 16bit binary number
                # see set_drive_settings in hardware.py for details

                self.feed_constant_mm_per_rot = (telegram[20] << 8 | telegram[19]) / 100
                self.log.debug(
                    f"Set mock controller to have feed constant of {self.feed_constant_mm_per_rot}"
                    f" mm per rotation"
                )
            elif telegram[14] == 2:
                # setting shaft revs, which should only ever be 1
                # because it's hard coded intentionally.
                shaft_revs = telegram[19]
                assert shaft_revs == 1
                self.log.debug(
                    f"Set mock controller to have shaft revs of {shaft_revs} per feed constant"
                )
            else:
                raise KeyError(f"Got unsupported value of {telegram[14]} in byte 14")
            # can now return a handshake
            _response_telegrams = [derive_handshake(self.cmd)]
            return _response_telegrams

        # 6099h_01h Homing speeds Switch --> speed at which it homes
        # for a switch
        # This is in RPM in the controller
        if telegram[12] == 96 and telegram[13] == 153:
            self.log.debug("Interpreted 6099h (Homing Speeds) telegram")
            if telegram[14] == 1:
                # speed at which it searches for switch
                self.homing_speed_switch_rpm = telegram[20] << 8 | telegram[19]
                self.log.debug(
                    f"Set mock controller to have homing switch speed of {self.homing_speed_switch_rpm} rpm"
                )
            elif telegram[14] == 2:
                # Speed at which it searches for the zero point
                self.homing_speed_zero_rpm = telegram[20] << 8 | telegram[19]
                self.log.debug(
                    f"Set mock controller to have homing zero point speed of {self.homing_speed_zero_rpm} rpm"
                )
            else:
                raise KeyError(f"Got unsupported value of {telegram[14]} in byte 14")
            # can now return a handshake
            _response_telegrams = [derive_handshake(self.cmd)]
            return _response_telegrams

        # 609Ah Homing acceleration
        # Needs to be in rpm/min^2
        if telegram[12] == 96 and telegram[13] == 154:
            self.log.debug("Interpreted 609Ah (Homing Acceleration) telegram")
            # acceleration used when searching
            self.homing_accel_rpm_per_min2 = (
                telegram[21] << 16 | telegram[20] << 8 | telegram[19]
            )
            self.log.debug(
                f"Set mock controller to have homing acceleration of {self.homing_accel_rpm_per_min2} "
                f"rpm/min^2"
            )
            # can now return a handshake
            _response_telegrams = [derive_handshake(self.cmd)]
            return _response_telegrams

        # 6081h Profile Velocity
        # This is in RPM in the controller
        if telegram[12] == 96 and telegram[13] == 129:
            self.log.debug("Interpreted 6081h (Profile Velocity) telegram")

            # speed at which it searches for switch
            self.motion_speed_rpm = telegram[20] << 8 | telegram[19]
            self.motion_speed_mm_per_s = (
                self.motion_speed_rpm * self.feed_constant_mm_per_rot
            )
            self.log.debug(
                f"Set mock controller to have motion speed of {self.motion_speed_rpm} rpm"
            )

            # can now return a handshake
            _response_telegrams = [derive_handshake(self.cmd)]
            return _response_telegrams

        # 6083h Profile Acceleration
        # Needs to be in rpm/min^2
        if telegram[12] == 96 and telegram[13] == 131:
            self.log.debug("Interpreted 6083h (Profile Acceleration) telegram")
            # acceleration used when searching
            self.motion_accel_rpm_per_min2 = (
                telegram[21] << 16 | telegram[20] << 8 | telegram[19]
            )
            self.log.debug(
                f"Set mock controller to have motion acceleration of {self.motion_accel_rpm_per_min2} "
                f"rpm/min^2"
            )
            # can now return a handshake
            _response_telegrams = [derive_handshake(self.cmd)]
            return _response_telegrams

        # 607Ah Target Position
        # This is in mm in the controller
        if telegram[12] == 96 and telegram[13] == 122:
            self.log.debug("Interpreted 607Ah (Target Position) telegram")

            # Set new target position
            self.target_pos = (
                telegram[22] << 24
                | telegram[21] << 16
                | telegram[20] << 8
                | telegram[19]
            ) / 100

            # can now return a handshake
            _response_telegrams = [derive_handshake(self.cmd)]
            return _response_telegrams

        # 6064h Position Actual Value
        # this returns values in mm, multiplied by 100

        if telegram[12] == 96 and telegram[13] == 100:
            self.log.debug("Interpreted 6064h (Get Position) telegram")

            # return_telegram contains current position in bytes 19-22
            # has a factor of 100 included for precision that must be removed
            _value = round(self.current_pos * 100)
            byte19 = _value & 0b11111111
            byte20 = (_value >> 8) & 0b11111111
            byte21 = (_value >> 16) & 0b11111111
            byte22 = _value >> 24

            _response = list(self.cmd[0:19])
            _response[5] = 17
            _response.extend([byte19, byte20, byte21, byte22])

            response_telegrams = [_response]
            return response_telegrams
