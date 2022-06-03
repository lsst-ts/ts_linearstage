__all__ = ["IgusLinearStageStepper"]

import asyncio
import time
import logging

from lsst.ts import salobj, utils
from lsst.ts.LinearStage.mocks.mock_igusDryveController import MockIgusDryveController
from lsst.ts.LinearStage.controllers.igus_dryve.igus_utils import (
    read_telegram,
    derive_handshake,
    interpret_read_telegram,
)

from lsst.ts.LinearStage.controllers.igus_dryve.igusDryveTelegrams import (
    telegrams_write,
    telegrams_read,
    # telegrams_read_errs,
)

_LOCAL_HOST = "127.0.0.1"
_STD_TIMEOUT = 20  # standard timeout

logging.basicConfig()
logger = logging.getLogger(__name__)


class IgusLinearStageStepper:
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

    def __init__(self, simulation_mode, log) -> None:
        self.log = log.getChild("IgusLinearStageStepper")
        self.connected = False
        self.commander = None
        self.mock_ctrl = None  # mock controller, or None of not constructed
        # Task that waits while connecting to the TCP/IP controller.
        self.connect_task = utils.make_done_future()
        self.reader = None
        self.writer = None
        self.cmd_lock = asyncio.Lock()
        self.connection_timeout = 5
        self.position = None
        self.status = None
        self.mode_num = None

        self.simulation_mode = bool(simulation_mode)

        self.log.debug(
            f"Initialized IgusLinearStageStepper, simulation mode is {self.simulation_mode}"
        )

    def configure(self, config):
        self.port = config.socket_port
        self.address = config.socket_address

        # feed rate *must* be in mm per rotation
        self.feed_constant = config.feed_rate
        self.homing_speed = config.homing_speed
        self.homing_acceleration = config.homing_acceleration
        self.homing_timeout = config.homing_timeout
        self.motion_speed = config.motion_speed
        self.motion_acceleration = config.motion_acceleration
        self.maximum_stroke = config.maximum_stroke

    async def connect(self):
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
        if self.check_connected:
            raise RuntimeError("Already connected")

        if self.simulation_mode == 1:
            # Handle issue where ports lower than 1024 are protected and
            # can't be bound.
            self.log.info(
                "In simulation, so must set port for TCP/IP "
                "connection to be auto selected."
            )
            self.port = 0
            await self.start_mock_ctrl()
            host = _LOCAL_HOST
        else:
            host = self.address
        try:
            async with self.cmd_lock:
                if self.simulation_mode != 0:
                    if self.mock_ctrl is None:
                        raise RuntimeError(
                            "In simulation mode but no mock controller found."
                        )
                port = self.port
                connect_coro = asyncio.open_connection(host=host, port=port)
                self.reader, self.writer = await asyncio.wait_for(
                    connect_coro, timeout=self.connection_timeout
                )
            self.log.debug(f"Connected to Dryve at {host} on port {port}")
            self.connected = True

        except Exception:
            err_msg = f"Could not open connection to host={host}, port={port}"
            self.log.exception(err_msg)
            raise RuntimeError(err_msg)

        # Now verify that controller is enabled (DI7 is high)
        # This must be done from the controller GUI or by sending a 24V
        # signal to the input.
        response = await self.retrieve_status()

        # Check that byte 20 is has bits 0,1,2 set
        if not (response[20] & 0b111):
            # Disconnect and raise error
            await self.disconnect()
            err_msg = (
                "Controller is not enabled. DI7 must be set to high "
                f"using the Igus GUI. Status response was {response}"
            )
            raise RuntimeError(err_msg)

    @property
    def check_connected(self):
        if None in (self.reader, self.writer):
            return False
        return True

    async def disconnect(self):
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
        self.connected = False

    async def start_mock_ctrl(self):
        """Start the mock controller.

        The simulation mode must be 1.
        Port gets randomized automatically if less than 1024 due to
        reserved port restrictions.
        """

        assert self.simulation_mode == 1
        port = self.port
        host = _LOCAL_HOST
        self.mock_ctrl = MockIgusDryveController(port=port, host=host, log=self.log)
        server_host, server_port = await asyncio.wait_for(
            self.mock_ctrl.start(), timeout=2
        )
        self.log.debug(
            f"Started Mock TCP/IP Server on host {server_host} and port {server_port}."
        )
        self.port = server_port

    async def stop_mock_ctrl(self):
        """Stop the mock controller, if running."""
        mock_ctrl = self.mock_ctrl
        self.mock_ctrl = None
        if mock_ctrl:
            await mock_ctrl.stop()

    async def enable_motor(self, value):
        """This method enables the motor and gets it ready to move.
        This includes transitioning the controller into the enabled/ready
        state and removing the brake (if appropriate).

        FIXME: This should also remove any fault conditions

        Parameters
        ----------
        value : `bool`
            True to enable the motor, False to disable the motor.
        """
        self.log.debug(f"Inside enable_motor with value set to {value}")

        if value:
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
        else:
            # make sure we're in position mode
            await self.set_mode("position")

            # Disable the motor
            self.log.debug("From enable_motor, sending Shutdown")
            await self.send_telegram(
                telegrams_write["shutdown"], return_response=False, check_handshake=True
            )
            await self.poll_until_result([telegrams_read["ready_to_switch_on"]])

    async def set_drive_settings(self):
        """The dryve requires numerous parameters to be set, all of which
        reside in the config file.
        This method sets the parameters right after set to the
        operation_enabled state"""

        self.log.debug("Applying configuration parameters to dryve controller")

        # multiplication factor required if we want 0.01 mm precision
        # feed constant and all acceleration, speed and position specs must
        # be multiplied by this number
        _multi_factor = 100

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

        _feed_constant = round(self.feed_constant * _multi_factor)
        if _feed_constant > 2**16:
            # Catch this here because diagnosing the error is tough
            raise NotImplementedError(
                f"Value for given for feed constant of {self.feed_constant}"
                f" exceeds limit of {(2 ** 16) / _multi_factor}"
            )
        byte19 = _feed_constant & 0b11111111
        byte20 = _feed_constant >> 8
        telegram = tuple(
            [
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
            ]
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
        telegram = tuple(
            [0, 0, 0, 0, 0, 14, 0, 43, 13, 1, 0, 0, 96, 146, 2, 0, 0, 0, 1, 1]
        )
        await self.send_telegram(telegram, return_response=False, check_handshake=True)

        # Now set homing values
        # 6099h_01h Homing speeds Switch --> speed at which it searches
        # for a switch
        # This needs to be in RPM, but the config file
        # (and self.feed_constant) is in mm/s
        _homing_speed_rpm = round(
            self.homing_speed / self.feed_constant * 60 * _multi_factor
        )
        if _homing_speed_rpm > 2**16:
            # Catch this here because diagnosing the error is tough
            raise NotImplementedError(
                f"Value for given for feed constant of {self.homing_speed}"
                f" exceeds limit of {(2 ** 16) / self.feed_constant * 60 * _multi_factor}"
            )
        byte19 = _homing_speed_rpm & 0b11111111
        byte20 = _homing_speed_rpm >> 8
        telegram = tuple(
            [
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
            ]
        )
        self.log.debug(
            f"About to send 6099h_01h, homing switch speed telegram of {telegram}"
        )
        await self.send_telegram(telegram, return_response=False, check_handshake=True)

        # 6099h_02h Homing speeds Zero --> Speed at which it searches for zero
        # just take half the homing speed
        _homing_speed_zero_rpm = round(_homing_speed_rpm / 2.0)
        byte19 = _homing_speed_zero_rpm & 0b11111111
        byte20 = _homing_speed_zero_rpm >> 8
        telegram = tuple(
            [
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
            ]
        )
        self.log.debug(
            f"About to send 6099h_02h, homing speed zero telegram of {telegram}"
        )
        await self.send_telegram(telegram, return_response=False, check_handshake=True)

        # 609Ah Homing acceleration
        # Needs to be in rpm/min^2
        _homing_accel_rpm = round(
            self.homing_acceleration / self.feed_constant * 60 * 60 * _multi_factor
        )

        byte19 = _homing_accel_rpm & 0b11111111
        byte20 = (_homing_accel_rpm >> 8) & 0b11111111
        byte21 = _homing_accel_rpm >> 16
        telegram = tuple(
            [
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
            ]
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
        _motion_speed_rpm = round(self.motion_speed * _multi_factor)
        if _motion_speed_rpm > 2**16:
            # Catch this here because diagnosing the error is tough
            raise NotImplementedError(
                f"Value for given for feed constant of {self.motion_speed}"
                f" exceeds limit of {(2 ** 16) / self.feed_constant * 60 * _multi_factor}"
            )
        byte19 = _motion_speed_rpm & 0b11111111
        byte20 = _motion_speed_rpm >> 8
        telegram = tuple(
            [
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
            ]
        )
        self.log.debug(
            f"About to send 6081h, Profile Velocity telegram of {telegram}, "
            f"which has value of {_motion_speed_rpm} rpm"
        )
        await self.send_telegram(telegram, return_response=False, check_handshake=True)

        # 6083h Profile Acceleration
        # Needs to be in mm/s^2
        # Must be multiplied by 100 (_multi_factor)
        _motion_accel_rpm = round(self.motion_acceleration * _multi_factor)

        byte19 = _motion_accel_rpm & 0b11111111
        byte20 = (_motion_accel_rpm >> 8) & 0b11111111
        byte21 = _motion_accel_rpm >> 16
        telegram = tuple(
            [
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
            ]
        )
        self.log.debug(
            f"About to send 6083h, profile acceleration telegram of {telegram}, "
            f"which has value of {_motion_accel_rpm} rpm/min^2"
        )
        await self.send_telegram(telegram, return_response=False, check_handshake=True)

    async def poll_until_result(
        self,
        results,
        cmd=telegrams_write["status_request"],
        freq=2,
        timeout=_STD_TIMEOUT,
        byte19=None,
        byte20=None,
    ):
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
        receipt = None
        attempts = 0
        while receipt not in results:
            # receipt = None
            receipt = await self.send_telegram(
                cmd, timeout=timeout, return_response=True, check_handshake=False
            )
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
                    raise TimeoutError(
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

    async def move_absolute(self, value, timeout=20):
        """This method moves the linear stage absolutely by the number of
        steps away from the zero (homed) position.
        i.e. value=10 would mean the stage would move 10 millimeters away from
        the start.

        Parameters
        ----------
        value : `float`
            The number of millimeters to move the stage.

        timeout : `float`
            Time to wait for stage to be in position before raising an
            exception.
            Default is 20s

        Returns
        -------

        """

        # Check the demand is within the allowed range
        # Note that this may permit the hitting of limit switches
        # the CSC limits the range based on configurations
        if value < 0 or value > self.maximum_stroke:
            raise ValueError(
                f"Demanded position of {value} is not between zero and {self.maximum_stroke}"
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
        byte19 = _value & 0b11111111
        byte20 = (_value >> 8) & 0b11111111
        byte21 = (_value >> 16) & 0b11111111
        byte22 = _value >> 24
        _telegram = tuple(
            [
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
            ]
        )

        await self.send_telegram(
            _telegram, check_handshake=True, return_response=False, timeout=2
        )
        # reset the start bit
        await self.send_telegram(telegrams_write["enable_operation"])
        # start motion
        self.log.debug(f"Starting to move to position {value} mm")
        await self.send_telegram(telegrams_write["start_motion"])
        # Now poll until target is reached
        await self.poll_until_result(
            [telegrams_read["target_reached"]], timeout=timeout
        )

    async def move_relative(self, value, timeout=20):
        """This method moves the linear stage relative to the current position.
        The method basically wraps the absolute positioning code.

        Parameters
        ----------
        value :
            The number of millimeters to move the stage.

        Returns
        -------

        """

        target_position = self.position + value
        await self.move_absolute(target_position, timeout=20)

    async def set_mode(self, mode):
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
        _telegram = tuple(
            [
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
            ]
        )

        await self.send_telegram(
            _telegram, check_handshake=True, return_response=False, timeout=2
        )
        expected_result = tuple(
            [
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
            ]
        )
        # Now ask for mode and it must return the requested mode
        await self.poll_until_result([expected_result], cmd=telegrams_write["get_mode"])
        self.log.debug(f"Mode set to {mode}")

    async def get_home(self):
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
            [telegrams_read["target_reached"]], timeout=self.homing_timeout
        )
        # set position profiling mode (1 on byte 19)
        await self.set_mode("position")

    def check_reply(self, reply):
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

    async def get_position(self):
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

        # response telegram returns it in bytes 19-22
        # is a factor of 100 inflated
        position = (
            response_telegram[22] << 24
            | response_telegram[21] << 16
            | response_telegram[20] << 8
            | response_telegram[19]
        ) / 100.0

        return position

    async def retrieve_status(self):
        """This method requests the status of the controller.
        This is statusword 6041h in the igus manual

        Parameters
        ----------
        reply :
            This is the reply that is to be checked.

        Returns
        -------
        response : `list`
            Returns list, as a tuple, returned from the controller.
        """

        response = await self.send_telegram(
            telegrams_write["status_request"],
            check_handshake=False,
            return_response=True,
        )
        self.log.debug(f"Sent status request, received {response}")
        return response

    async def publish(self):
        """Publish the telemetry of the stage."""

        self.position = await self.get_position()
        self.status = await self.retrieve_status()

    def stop(self):
        """Stops the movement of the stage.
        This should never need to be used since movement commands do not
        return until completed"""
        raise NotImplementedError

    async def send_telegram(
        self, cmd, return_response=True, check_handshake=False, timeout=_STD_TIMEOUT
    ):
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
            FIXME: remove this functionality and always return a response

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

        async with self.cmd_lock:

            self.writer.write(bytearray(cmd))
            await self.writer.drain()
            self.log.debug(f"Sent telegram {cmd}")

            if check_handshake or return_response:
                try:
                    line = await read_telegram(self.reader, timeout=timeout)
                    self.log.debug(f"Received response telegram of {list(line)}")

                except Exception as e:
                    if isinstance(e, asyncio.streams.IncompleteReadError):
                        err_msg = "TCP/IP controller exited"
                    else:
                        err_msg = "TCP/IP read failed"
                    self.log.exception(err_msg)
                    await self.disconnect()
                    # self.fault(code=2, report=f"{err_msg}: {e}")
                    raise salobj.ExpectedError(err_msg)

                # telegrams should always be tuples
                # required for hashing purposes
                data = tuple(list(line))

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
