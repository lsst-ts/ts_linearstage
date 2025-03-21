# This file is part of ts_linearstage.
#
# Developed for the Vera C. Rubin Observatory Telescope and Site Systems.
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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

__all__ = ["Igus"]

import asyncio
import logging
import time
import types
import typing

import numpy as np
import yaml
from lsst.ts import salobj, tcpip, utils

from ..mocks import MockIgusDryveController
from .stage import Stage
from .telegrams import telegrams_read, telegrams_write  # telegrams_read_errs,
from .utils import derive_handshake, interpret_read_telegram, read_telegram

_LOCAL_HOST = tcpip.LOCAL_HOST
_STD_TIMEOUT = 20  # standard timeout


class Igus(Stage):
    """A class representing the Igus linear stage devices.
    These devices are driven by stepper motors over a socket
    using the Dryve v1 controller


    Parameters
    ----------

    simulation_mode : `bool`
        Is the stage in simulation mode.

    log : `logging.Logger`
        A log for the class.

    Attributes
    ----------

    connected : `bool`
        Is the stage connected.

    commander : ``
        Commands the Dryve device via TCP/IP device.

    port :
        The port used to establish the socket connection.

    address :
        The address of the dryve controller.

    position : `str`
        This holds the position of the linear stage. It starts at none as
        device requires homing to be done before it can be moved.

    status : `str`
        This holds the status of the linear stage controller. More details
        can be found in the dryve manual.

    simulation_mode : `bool`
        Is the hardware in simulation mode.

    """

    def __init__(
        self, config: types.SimpleNamespace, simulation_mode: int, log: logging.Logger
    ) -> None:
        super().__init__(config=config, simulation_mode=simulation_mode, log=log)
        self.mock_ctrl: MockIgusDryveController | None = (
            None  # mock controller, or None of not constructed
        )
        # Task that waits while connecting to the TCP/IP controller.
        self.connect_task: asyncio.Task = utils.make_done_future()
        # FIXME DM-45058 Convert to a tcpip.Client
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.cmd_lock: asyncio.Lock = asyncio.Lock()
        self.connection_timeout: int = 5
        self.position: list[float] = [0.0]
        self.status: tuple = tuple()
        self.mode_num: int = 0

        self.log.debug(
            f"Initialized IgusLinearStageStepper, simulation mode is {self.simulation_mode}"
        )

    async def connect(self) -> None:
        """Connect to the Igus Dryve controller's TCP/IP port.
        Note that dryve must be configured to
        use MODBUS TCP, with a unit identifier of 1.
        The method also verifies that the controller is setup
        correctly to receive commands.

        Start the mock controller, if simulating.

        Raises
        ------

        RuntimeError:
            Occurs when TCP/IP connection fails, or, when the connection
            succeeds but the controller is not in the correct configuration
            due to DI7 not being in the enabled state.
        """

        self.log.debug(
            f"Connecting to Igus Dryve, simulation is {bool(self.simulation_mode)}"
        )
        if self.connected:
            raise RuntimeError("Already connected")

        if self.simulation_mode == 1:
            # Handle issue where ports lower than 1024 are protected and
            # can't be bound.
            self.log.info(
                "In simulation, so must set port for TCP/IP "
                "connection to be auto selected."
            )
            self.config.socket_port = 0
            await self.start_mock_ctrl()
            host: str = _LOCAL_HOST
        else:
            host = self.config.socket_address
        try:
            async with self.cmd_lock:
                if self.simulation_mode != 0:
                    if self.mock_ctrl is None:
                        raise RuntimeError(
                            "In simulation mode but no mock controller found."
                        )
                port: int = self.config.socket_port
                connect_coro: typing.Coroutine[
                    typing.Any,
                    typing.Any,
                    tuple[asyncio.StreamReader, asyncio.StreamWriter],
                ] = asyncio.open_connection(host=host, port=port)
                self.reader, self.writer = await asyncio.wait_for(
                    connect_coro, timeout=self.connection_timeout
                )
            self.log.debug(f"Connected to Dryve at {host} on port {port}")

        except Exception:
            err_msg = f"Could not open connection to host={host}, port={port}"
            self.log.exception(err_msg)
            raise RuntimeError(err_msg)

        # Now verify that controller is enabled (DI7 is high)
        # This must be done from the controller GUI or by sending a 24V
        # signal to the input.
        response: tuple = await self.retrieve_status()

        # Check that byte 20 is has bits 0,1,2 set
        # FIXME DM-45058 add to wizardry.py
        if not (response[20] & 0b111):
            # Disconnect and raise error
            await self.disconnect()
            err_msg = (
                "Controller is not enabled. DI7 must be set to high "
                f"using the Igus GUI. Status response was {response}"
            )
            raise RuntimeError(err_msg)

    @property
    def connected(self) -> bool:
        """Is the client connected?"""
        # FIXME DM-45058 Change to Client.connected
        if None in (self.reader, self.writer):
            return False
        return True

    async def disconnect(self) -> None:
        """Disconnect from the TCP/IP controller, if connected, and stop
        the mock controller, if running.
        """
        self.log.debug("Disconnecting from TCP/IP connection")
        self.connect_task.cancel()
        writer = self.writer
        self.reader = None
        self.writer = None
        if writer:
            try:
                writer.write_eof()
                await asyncio.wait_for(writer.drain(), timeout=2)
            finally:
                writer.close()
        await self.stop_mock_ctrl()

    async def start_mock_ctrl(self) -> None:
        """Start the mock controller.

        The simulation mode must be 1.
        Port gets randomized automatically if less than 1024 due to
        reserved port restrictions.
        """

        assert self.simulation_mode == 1
        port = self.config.socket_port
        host = _LOCAL_HOST
        self.mock_ctrl = MockIgusDryveController(port=port, host=host, log=self.log)
        server_host, server_port = await asyncio.wait_for(
            self.mock_ctrl.start(), timeout=2
        )
        self.log.debug(
            f"Started Mock TCP/IP Server on host {server_host} and port {server_port}."
        )
        self.config.socket_port = server_port

    async def stop_mock_ctrl(self) -> None:
        """Stop the mock controller, if running."""
        mock_ctrl = self.mock_ctrl
        self.mock_ctrl = None
        if mock_ctrl:
            await mock_ctrl.stop()

    async def enable_motor(self) -> None:
        """This method enables the motor and gets it ready to move.
        This includes transitioning the controller into the enabled/ready
        state and removing the brake (if appropriate).

        FIXME: DM-45058 This should also remove any fault conditions

        Parameters
        ----------
        value : `bool`
            True to enable the motor, False to disable the motor.
        """
        # Enable the motor
        # first send shutdown
        self.log.debug("From enable_motor, sending Shutdown")
        await self.send_telegram(
            telegrams_write["shutdown"], return_response=False, check_handshake=True
        )
        await self.poll_until_result(
            [telegrams_read["ready_to_switch_on"]],  # byte20=6
        )
        # make sure we're in position mode
        await self.set_mode("position")

        # then switch on
        self.log.debug("From enable_motor, sending switch_on")
        await self.send_telegram(
            telegrams_write["switch_on"],
            return_response=False,
            check_handshake=True,
        )
        await self.poll_until_result([telegrams_read["switched_on"]])
        # then enable
        self.log.debug("From enable_motor, sending enable_operation")
        await self.send_telegram(
            telegrams_write["enable_operation"],
            return_response=False,
            check_handshake=True,
        )
        await self.poll_until_result([telegrams_read["operation_enabled"]])

        # now set all the required drive parameters
        await self.set_drive_settings()

    async def disable_motor(self) -> None:
        """Disable the motor."""
        # make sure we're in position mode
        await self.set_mode("position")

        # Disable the motor
        self.log.debug("From enable_motor, sending Shutdown")
        await self.send_telegram(
            telegrams_write["shutdown"], return_response=False, check_handshake=True
        )
        await self.poll_until_result([telegrams_read["ready_to_switch_on"]])

    async def set_drive_settings(self) -> None:
        """The dryve requires numerous parameters to be set, all of which
        reside in the config file.
        This method sets the parameters right after set to the
        operation_enabled state"""

        self.log.debug("Applying configuration parameters to dryve controller")

        # multiplication factor required if we want 0.01 mm precision
        # feed constant and all acceleration, speed and position specs must
        # be multiplied by this number
        _multi_factor: int = 100

        # Start with feed rate values
        # 6092h_01h Feed constant Subindex 1 (Feed)
        # See manual
        # How to get bytes 19 and 20 from the desired value?
        # See manual section 6.5.2, and 6092h documentation (pg 95)
        # for a value of 60 mm, need to multiply by 100, then split 16-bit
        # binary value into two 8-bit bytes.
        # Byte 19 has the rightmost 8 bits, byte 20 the leftmost 8
        # byte19 = 6000 & 0b11111111 # gives integer value (112) of
        # last 8 bits in binary
        # byte20 = 6000 >> 8 # bit shifts 8 bits and gives int value
        # of remaining 8 bits (23)
        # sendCommand(bytearray([0, 0, 0, 0, 0, 15, 0, 43, 13, 1, 0, 0, 96,
        #                        146, 1, 0, 0, 0, 2, 112, 23]))

        _feed_constant: int = round(self.config.feed_rate * _multi_factor)
        if _feed_constant > 2**16:
            # Catch this here because diagnosing the error is tough
            raise NotImplementedError(
                f"Value for given for feed constant of {self.config.feed_rate}"
                f" exceeds limit of {(2 ** 16) / _multi_factor}"
            )
        # FIXME DM-45058 Add to wizardry.py
        byte19: int = _feed_constant & 0b11111111
        # FIXME DM-45058 Add to wizardry.py
        byte20: int = _feed_constant >> 8
        telegram: tuple = (
            0,
            0,
            0,
            0,
            0,
            15,
            0,
            43,
            13,
            1,
            0,
            0,
            96,
            146,
            1,
            0,
            0,
            0,
            2,
            byte19,
            byte20,
        )
        self.log.debug(
            f"About to send feed rate telegram of {telegram}, "
            f"which has value of {_feed_constant} mm, which includes a "
            f"multiplication factor of {_multi_factor}"
        )
        await self.send_telegram(telegram, return_response=False, check_handshake=True)

        # 6092h_02h Feed constant Subindex 2 (Shaft revolutions)
        # Set shaft revolutions to 1; refer to manual (Byte 19 = 1)
        # This is hardcoded intentionally as feed rate in config file is
        # PER ROTATION
        telegram = (0, 0, 0, 0, 0, 14, 0, 43, 13, 1, 0, 0, 96, 146, 2, 0, 0, 0, 1, 1)
        await self.send_telegram(telegram, return_response=False, check_handshake=True)

        # Now set homing values
        # 6099h_01h Homing speeds Switch --> speed at which it searches
        # for a switch
        # This needs to be in RPM, but the config file
        # (and self.config.feed_constant) is in mm/s
        _homing_speed_rpm = round(
            self.config.homing_speed / self.config.feed_rate * 60 * _multi_factor
        )
        if _homing_speed_rpm > 2**16:
            # Catch this here because diagnosing the error is tough
            raise NotImplementedError(
                f"Value for given for feed constant of {self.config.homing_speed}"
                f" exceeds limit of {(2 ** 16) / self.config.feed_rate * 60 * _multi_factor}"
            )
        # FIXME DM-45058 Add to wizardry.py
        byte19 = _homing_speed_rpm & 0b11111111
        # FIXME DM-45058 Add to wizardry.py
        byte20 = _homing_speed_rpm >> 8
        telegram = (
            0,
            0,
            0,
            0,
            0,
            15,
            0,
            43,
            13,
            1,
            0,
            0,
            96,
            153,
            1,
            0,
            0,
            0,
            2,
            byte19,
            byte20,
        )
        self.log.debug(
            f"About to send 6099h_01h, homing switch speed telegram of {telegram}"
        )
        await self.send_telegram(telegram, return_response=False, check_handshake=True)

        # 6099h_02h Homing speeds Zero --> Speed at which it searches for zero
        # just take half the homing speed
        _homing_speed_zero_rpm = round(_homing_speed_rpm / 2.0)
        # FIXME DM-45058 Add to wizardry.py
        byte19 = _homing_speed_zero_rpm & 0b11111111
        byte20 = _homing_speed_zero_rpm >> 8
        telegram = (
            0,
            0,
            0,
            0,
            0,
            15,
            0,
            43,
            13,
            1,
            0,
            0,
            96,
            153,
            2,
            0,
            0,
            0,
            2,
            byte19,
            byte20,
        )
        self.log.debug(
            f"About to send 6099h_02h, homing speed zero telegram of {telegram}"
        )
        await self.send_telegram(telegram, return_response=False, check_handshake=True)

        # 609Ah Homing acceleration
        # Needs to be in rpm/min^2
        _homing_accel_rpm = round(
            self.config.homing_acceleration
            / self.config.feed_rate
            * 60
            * 60
            * _multi_factor
        )

        # FIXME DM-45058 Add to wizardry.py
        byte19 = _homing_accel_rpm & 0b11111111
        byte20 = (_homing_accel_rpm >> 8) & 0b11111111
        byte21 = _homing_accel_rpm >> 16
        telegram = (
            0,
            0,
            0,
            0,
            0,
            16,
            0,
            43,
            13,
            1,
            0,
            0,
            96,
            154,
            0,
            0,
            0,
            0,
            3,
            byte19,
            byte20,
            byte21,
        )
        self.log.debug(
            f"About to send 609Ah, homing acceleration telegram of {telegram}, "
            f"which has value of {_homing_accel_rpm} rpm/min^2"
        )
        await self.send_telegram(telegram, return_response=False, check_handshake=True)

        # Now set standard motion parameters (speed and acceleration)
        # in the controller

        # 6081h Profile Velocity
        # Must be multiplied by 100 (_multi_factor)
        # This needs to be in mm/s
        _motion_speed_rpm = round(self.config.motion_speed * _multi_factor)
        if _motion_speed_rpm > 2**16:
            # Catch this here because diagnosing the error is tough
            raise NotImplementedError(
                f"Value for given for feed constant of {self.config.motion_speed}"
                f" exceeds limit of {(2 ** 16) / self.config.feed_constant * 60 * _multi_factor}"
            )
        # FIXME DM-45058 Add to wizardry.py
        byte19 = _motion_speed_rpm & 0b11111111
        byte20 = _motion_speed_rpm >> 8
        telegram = (
            0,
            0,
            0,
            0,
            0,
            15,
            0,
            43,
            13,
            1,
            0,
            0,
            96,
            129,
            0,
            0,
            0,
            0,
            2,
            byte19,
            byte20,
        )
        self.log.debug(
            f"About to send 6081h, Profile Velocity telegram of {telegram}, "
            f"which has value of {_motion_speed_rpm} rpm"
        )
        await self.send_telegram(telegram, return_response=False, check_handshake=True)

        # 6083h Profile Acceleration
        # Needs to be in mm/s^2
        # Must be multiplied by 100 (_multi_factor)
        _motion_accel_rpm = round(self.config.motion_acceleration * _multi_factor)

        # FIXME DM-45058 Add to wizardry.py
        byte19 = _motion_accel_rpm & 0b11111111
        byte20 = (_motion_accel_rpm >> 8) & 0b11111111
        byte21 = _motion_accel_rpm >> 16
        telegram = (
            0,
            0,
            0,
            0,
            0,
            16,
            0,
            43,
            13,
            1,
            0,
            0,
            96,
            131,
            0,
            0,
            0,
            0,
            3,
            byte19,
            byte20,
            byte21,
        )
        self.log.debug(
            f"About to send 6083h, profile acceleration telegram of {telegram}, "
            f"which has value of {_motion_accel_rpm} rpm/min^2"
        )
        await self.send_telegram(telegram, return_response=False, check_handshake=True)

    async def poll_until_result(
        self,
        results: list[tuple],
        cmd: tuple = telegrams_write["status_request"],
        freq: int = 2,
        timeout: float = _STD_TIMEOUT,
        byte19: None | int = None,
        byte20: None | int = None,
    ) -> None:
        """Poll the controller and return when desired result is obtained
        or a timeout occurs.

        Because bytes 19 and 20 represent 8 status bits each. The byte19 and
        byte20 parameters represent how to verify that a minimal set of bits
        are active. For example, setting byte19 to `0b10111` (or 23) means
        that bits 0-2 and 5 must be set high to return True. Having more
        bits set as True has no effect.

        Parameters
        ----------
        results : `list`
            Telegrams(s) expected to be returned from controller that result
             in success

        cmd : `list`
            Command to be send to controller while polling. Default is to
            request status.

        freq : `float`
            Frequency at which to poll the controller. Default is 2 Hz.

        timeout: `float`
            Time for which to poll controller before raising an exception.
            Default is 5s
        byte19: `int`
            Minimal set of bits that must be high in byte 19
        byte20: `int`
            Minimal set of bits that must be high in byte 20
        """

        # Now poll for expectation
        self.log.debug("Starting to poll Controller.")
        start_time = time.time()
        attempts = 0
        receipt: tuple | None = None
        while receipt not in results:
            # receipt = None
            receipt = await self.send_telegram(
                cmd, timeout=timeout, return_response=True, check_handshake=False
            )
            if receipt is None:
                raise RuntimeError("Response not received.")
            self.log.debug(f"Polling received telegram of {receipt}")

            # The evaluation is probably best done using a for-loop
            # Can replace the following if required.
            for result in results:
                # Set bytes 19 and 20 as appropriate for comparison
                if len(result) >= 19 + 1:
                    _byte19 = byte19 if byte19 is not None else result[19]
                    if len(result) >= 20 + 1:
                        _byte20 = byte20 if byte20 is not None else result[20]

                # Check if first part of the status is correct
                if receipt[0:18] != result[0:18]:
                    # Now check if byte19 and byte20 are satisfied
                    if len(result) >= 19 + 1:
                        #
                        b19_isTrue = (
                            True if ((receipt[19] & _byte19) == receipt[19]) else False
                        )
                        if len(result) == 19 + 1 and b19_isTrue:
                            # Status is only 19 characters and is the
                            # same, can break
                            break
                        elif len(result) >= 20 + 1:
                            b20_isTrue = (
                                True
                                if ((receipt[20] & _byte20) == receipt[20])
                                else False
                            )
                            if b19_isTrue and b20_isTrue:
                                # All bits satisfied, Can break
                                break

                total_time = time.time() - start_time
                if total_time > timeout:
                    # try to interpret the last message
                    interpretation = interpret_read_telegram(receipt, self.mode_num)
                    raise asyncio.TimeoutError(
                        f"Polling time exceeded timeout of {timeout}s "
                        f"without receiving expected result of: \n {result} \n,"
                        f"last received response was: \n {receipt}.\n"
                        f"{interpretation}"
                    )

                # Delay by frequency
                # This isn't ideal as it does not account for how long it
                # takes to receive the telegram
                # I imagine there is a better way to do this. It seems
                # unnecessary to evaluate the expression twice
                await asyncio.sleep(1.0 / freq)
                attempts += 1

            if byte19 is not None or byte20 is not None:
                self.log.debug(
                    f"Looking for \n {result} with bytes [19, 20] having a "
                    f"minimum of [{_byte19}, {_byte20}] set and got \n {receipt}"
                )
            else:
                self.log.debug(f"Looking for \n {receipt} and got \n {result}")

        self.log.debug("Received desired response!")

    def time_to_target(self, target: float) -> float:
        """Estimate the time to reach a target based on distance, speed
        and acceleration parameters.

        Parameters
        ----------
        target : `float`
            The number of millimeters of movement.

        Returns
        -------

        time_to_target : `float`
            The estimated number of seconds to reach the target.

        """
        dist_to_target = np.abs(target - self.position[0])

        # Calculate Distance to get to maximum speed
        dist_to_max_v = self.config.motion_speed**2 / (
            2 * self.config.motion_acceleration
        )

        # Consider case where maximum velocity is never reached
        # So will be accelerating and decelerating only
        if dist_to_target < 2 * dist_to_max_v:
            # Time accelerating for half the distance to the target would be
            # sqrt(2*(dist_to_target/2)/self.config.motion_acceleration)
            # but we simplify this and account for both accel and decel
            estimated_time = 2 * np.sqrt(
                dist_to_target / self.config.motion_acceleration
            )
        else:
            # Max velocity will be reached
            time_to_accelerate = np.sqrt(
                2 * dist_to_max_v / self.config.motion_acceleration
            )
            estimated_time = (
                2 * time_to_accelerate
                + (dist_to_target - 2 * dist_to_max_v) / self.config.motion_speed
            )

        self.log.info(f"Estimated time to target is {estimated_time:0.3f} seconds.")
        return estimated_time

    async def move_absolute(self, value: float, axis) -> None:
        """This method moves the linear stage absolutely by the number of
        steps away from the zero (homed) position.
        i.e. value=10 would mean the stage would move 10 millimeters away from
        the home position.

        Parameters
        ----------
        value : `float`
            The number of millimeters to move the stage.
        axis : `Axis`
            The axis to perform the command.

        Returns
        -------

        """

        # Check the demand is within the allowed range
        # Note that this may permit the hitting of limit switches
        # the CSC limits the range based on configurations
        if value < 0 or value > self.config.maximum_stroke:
            raise ValueError(
                f"Demanded position of {value} is not between zero and {self.config.maximum_stroke}"
            )

        # set the start signal bit to 0, so new positions can be demanded and
        # the new motion will start.
        await self.send_telegram(
            telegrams_write["enable_operation"],
            check_handshake=True,
            return_response=False,
        )

        # Set the desired position in mm
        # Uses command 607Ah (Target Position)
        # but must send a value multiplied by 100 to get precise movements
        _value = round(value * 100)
        # FIXME DM-45058 add to wizardry.py
        byte19 = _value & 0b11111111
        byte20 = (_value >> 8) & 0b11111111
        byte21 = (_value >> 16) & 0b11111111
        byte22 = _value >> 24
        _telegram = (
            0,
            0,
            0,
            0,
            0,
            17,
            0,
            43,
            13,
            1,
            0,
            0,
            96,
            122,
            0,
            0,
            0,
            0,
            4,
            byte19,
            byte20,
            byte21,
            byte22,
        )

        await self.send_telegram(
            _telegram, check_handshake=True, return_response=False, timeout=2
        )
        # reset the start bit
        await self.send_telegram(telegrams_write["enable_operation"])
        # start motion
        self.log.info(f"Starting to move to position {value} mm")
        movement_time = self.time_to_target(value)
        await self.send_telegram(telegrams_write["start_motion"])
        # Now poll until target is reached
        # FIXME DM-45058 Add to wizardry.py
        await self.poll_until_result(
            [telegrams_read["target_reached"]], timeout=movement_time + 5.0
        )

    async def move_relative(self, value: float, axis) -> None:
        """This method moves the linear stage relative to the current position.
        The method basically wraps the absolute positioning code.

        Parameters
        ----------
        value :
            The number of millimeters to move the stage.

        Returns
        -------

        """

        target_position = self.position[0] + value
        await self.move_absolute(target_position, axis)

    async def set_mode(self, mode: str) -> None:
        """Sets the mode for the igus controller.

        Only two modes are currently supported, homing, and
        position profiling.

        Parameters
        ----------

        mode : `string`
            Supported modes are: "undefined" "homing" "position"
        """
        # this uses the 6060h telegram

        if mode == "homing":
            self.mode_num = 6
        elif mode == "position":
            self.mode_num = 1
        else:
            raise KeyError(f"Mode of {mode} is not supported.")

        self.log.debug(f"Setting Mode to {mode}")

        # Set operation modes in object 6060h Modes of Operation
        _telegram = (
            0,
            0,
            0,
            0,
            0,
            14,
            0,
            43,
            13,
            1,
            0,
            0,
            96,
            96,
            0,
            0,
            0,
            0,
            1,
            self.mode_num,
        )

        await self.send_telegram(
            _telegram, check_handshake=True, return_response=False, timeout=2
        )
        expected_result = (
            0,
            0,
            0,
            0,
            0,
            14,
            0,
            43,
            13,
            0,
            0,
            0,
            96,
            97,
            0,
            0,
            0,
            0,
            1,
            self.mode_num,
        )
        # Now ask for mode and it must return the requested mode
        await self.poll_until_result([expected_result], cmd=telegrams_write["get_mode"])
        self.log.debug(f"Mode set to {mode}")

    async def home(self) -> None:
        """This method calls the homing method of the device which is used to
        establish a reference position.

        The method sets the mode to homing, then starts the motion to find the
        limit switch. Upon successful completion, it sets the mode to use
        positioning.

        """
        # This could be prettier. Create a assert_status function?
        _status = await self.retrieve_status()

        # if *not* in one of these status then raise an error
        if not (
            (_status == telegrams_read["operation_enabled"])
            or (_status == telegrams_read["target_reached"])
        ):
            raise RuntimeError(
                f"Igus stage status is incorrect. Must be "
                f'in "operation_enabled" or "target_reached" to'
                f" perform homing. Received {_status}."
            )

        # set homing mode (6 on byte 19)
        await self.set_mode("homing")

        # set the start signal bit to 0, so new positions can be demanded and
        # the new motion will start.
        await self.send_telegram(
            telegrams_write["enable_operation"],
            check_handshake=True,
            return_response=False,
        )

        # start motion
        self.log.debug("Starting motion")
        await self.send_telegram(telegrams_write["start_motion"])
        await self.poll_until_result(
            [telegrams_read["target_reached"]], timeout=self.config.homing_timeout
        )
        # set position profiling mode (1 on byte 19)
        await self.set_mode("position")

    def check_reply(self, reply) -> typing.NoReturn:
        """This method checks the reply for any warnings or errors and
        acknowledgement or rejection of the command.

        This is not yet implemented for the Igus stage.

        Parameters
        ----------
        reply :
            This is the reply that is to be checked.

        Returns
        -------

        """

        raise NotImplementedError

    async def get_position(self) -> float:
        """This method returns the position of the linear stage.
        This is statusword 6064h mentioned in the manual.


        Returns
        -------

        position : `float`
            Returns value (in mm) of current stage position.

        """

        # Get encoder position from 6064h
        # how do you know what this is?
        self.log.debug("Sending get_position telegram")
        response_telegram = await self.send_telegram(
            telegrams_write["get_position"], check_handshake=False
        )
        if response_telegram is None:
            raise RuntimeError("No response received.")

        # response telegram returns it in bytes 19-22
        # is a factor of 100 inflated
        position = (
            response_telegram[22] << 24
            | response_telegram[21] << 16
            | response_telegram[20] << 8
            | response_telegram[19]
        ) / 100.0

        return position

    async def retrieve_status(self) -> tuple:
        """This method requests the status of the controller.
        This is statusword 6041h in the igus manual

        Parameters
        ----------
        reply :
            This is the reply that is to be checked.

        Returns
        -------
        response : `tuple`
            Returns list, as a tuple, returned from the controller.
        """

        response: tuple | None = await self.send_telegram(
            telegrams_write["status_request"],
            check_handshake=False,
            return_response=True,
        )
        if response is None:
            raise RuntimeError("Response not received.")
        self.log.debug(f"Sent status request, received {response}")
        return response

    async def update(self) -> None:
        """Publish the telemetry of the stage."""

        self.position[0] = await self.get_position()
        self.status = await self.retrieve_status()

    def stop(self) -> typing.NoReturn:
        """Stops the movement of the stage.
        This should never need to be used since movement commands do not
        return until completed"""
        raise NotImplementedError

    async def send_telegram(
        self, cmd, return_response=True, check_handshake=False, timeout=_STD_TIMEOUT
    ) -> tuple | None:
        """Send a command to the TCP/IP controller and process its replies.

        Parameters
        ----------
        cmd : `list`
            The command to send,
            e.g. [0, 0, 0, 0, 0, 13, 0, 43, 13, 0, 0, 0,
            96, 65, 0, 0, 0, 0, 2]
            telegrams_write["status_request"]

        return_response : `bool`
            Return a response?
            FIXME:DM-45058 remove this functionality and always return response

        check_handshake : `bool`
            Check that the expected handshake was received from controller

        Raises
        ------
        salobj.ExpectedError
            If communication fails. Also an exception is logged,
            the CSC disconnects from the low level controller,
            and goes into FAULT state.
            If the wrong number of lines is read. Also a warning is logged.
        """
        if not self.connected:
            if salobj.State.ENABLED and not self.connect_task.done():
                await self.connect_task
            else:
                raise RuntimeError("Not connected and not trying to connect")

        if self.writer is None or self.reader is None:
            raise RuntimeError("Reader and/or writer are none.")

        async with self.cmd_lock:
            self.writer.write(bytearray(cmd))
            await self.writer.drain()
            self.log.debug(f"Sent telegram {cmd}")

            if check_handshake or return_response:
                try:
                    line = await read_telegram(self.reader, timeout=timeout)
                    self.log.debug(f"Received response telegram of {list(line)}")

                except Exception as e:
                    if isinstance(e, asyncio.IncompleteReadError):
                        err_msg = "TCP/IP controller exited"
                    else:
                        err_msg = "TCP/IP read failed"
                    self.log.exception(err_msg)
                    await self.disconnect()
                    # self.fault(code=2, report=f"{err_msg}: {e}")
                    raise salobj.ExpectedError(err_msg)

                # telegrams should always be tuples
                # required for hashing purposes
                data = tuple(line)

                if check_handshake:
                    expected_handshake = derive_handshake(cmd)
                    if data == expected_handshake:
                        self.log.debug("Handshake received successfully!")
                    else:
                        raise RuntimeError(
                            f"Handshake check desired but no handshake received. Received {data},"
                            f" but was expecting {expected_handshake}."
                        )

                if return_response:
                    return data
            return None

    @classmethod
    def get_config_schema(cls) -> dict:
        """Get the device specific config schema."""
        return yaml.safe_load(
            """
            $schema: http://json-schema.org/draft-07/schema#
            $id: https://github.com/lsst-ts/ts_LinearStage/master/python/lsst/ts/linearstage/config_schema.py
            title: Igus v1
            description: Schema for Igus configuration files
            type: object
            properties:
                socket_address:
                    type: string
                    format: hostname
                socket_port:
                    type: number
                feed_rate:
                    type: number
                maximum_stroke:
                    type: number
                homing_speed:
                    type: number
                homing_acceleration:
                    type: number
                homing_timeout:
                    type: number
                motion_speed:
                    type: number
                motion_acceleration:
                    type: number
            required:
                - socket_address
                - socket_port
                - feed_rate
                - maximum_stroke
                - homing_speed
                - homing_acceleration
                - homing_timeout
                - motion_speed
                - motion_acceleration
            additionalProperties: false
        """
        )
