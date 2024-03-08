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

__all__ = ["Zaber", "ZaberV2"]

import asyncio
import os
import pty
from unittest.mock import AsyncMock, MagicMock

import yaml
from lsst.ts import salobj
from lsst.ts.linearstage.mocks.mock_zaber_lst import LinearStageServer, MockSerial
from zaber import serial as zaber
from zaber_motion import FirmwareVersion, Units
from zaber_motion.ascii import Connection, DeviceIdentity
from zaber_motion.exceptions import CommandFailedException, ConnectionFailedException

from .stage import Stage

_LOCAL_HOST = "127.0.0.1"
_STD_TIMEOUT = 20  # standard timeout
_ZABER_MOVEMENT_TIME = 3  # time to wait for zaber to complete movement/homing


class ZaberV2(Stage):
    def __init__(self, config, log, simulation_mode):
        super().__init__(config, log, simulation_mode)
        self.client = None
        self.mock_server = None

    @property
    def connected(self):
        # Assume client is connected
        if self.client is not None:
            return True
        else:
            return False

    async def connect(self):
        if self.simulation_mode:
            self.mock_server = LinearStageServer(port=0, log=self.log)
            await self.mock_server.start_task
            self.config.port = self.mock_server.port
        try:
            self.client = Connection.open_tcp(
                host_name=self.config.hostname, port=self.config.port
            )
        except ConnectionFailedException:
            self.log.exception("Failed to connect to host/port.")
            raise RuntimeError(f"Unable to connect to host {self.config.hostname}.")
        self.device = self.client.get_device(self.config.daisy_chain_address)
        self.log.debug(f"{self.device=}")
        if self.simulation_mode:
            device_identity = DeviceIdentity()
            device_identity.axis_count = 1
            device_identity.device_id = 11111
            device_identity.serial_number = 22222
            device_identity.name = "Fake Device"
            device_identity.firmware_version = FirmwareVersion(
                major=7, minor=38, build=0
            )
            device_identity.is_modified = False
            device_identity.is_integrated = False
            self.device.__retrieve_identity = MagicMock(return_value=device_identity)
            self.device.__retrieve_is_identified = MagicMock(return_value=True)
            self.device.identify_async = AsyncMock(return_value=device_identity)
            self.device.identify = MagicMock(return_value=device_identity)
            self.device.__retrieve_identity()
            self.log.debug("Device patched.")
            self.log.debug(f"{self.device=}")
        await self.device.identify_async()
        self.log.debug(f"{self.device=}")

    async def disconnect(self):
        self.client.close()
        self.client = None
        self.device = None
        if self.simulation_mode:
            await self.mock_server.close()
            self.mock_server = None
        return super().disconnect()

    async def move_relative(self, value):
        for axis_index in range(self.device.axis_count):
            axis = self.device.get_axis(axis_index + 1)
            try:
                await axis.move_relative_async(
                    position=value, unit=Units.LENGTH_MILLIMETRES
                )
            except CommandFailedException:
                self.log.exception("Move relative failed.")
        return super().move_relative()

    async def move_absolute(self, value):
        device = self.device
        for axis_index in range(device.axis_count):
            axis = device.get_axis(axis_index + 1)
            try:
                axis.move_absolute(position=value, unit=Units.LENGTH_MILLIMETRES)
            except CommandFailedException:
                self.log.exception("Move absolute failed.")
        return super().move_absolute()

    async def home(self):
        device = self.device
        for axis_index in range(device.axis_count):
            axis = device.get_axis(axis_index + 1)
            try:
                axis.home()
            except CommandFailedException:
                self.log.exception("Home failed.")
        return super().home()

    async def enable_motor(self):
        device = self.device
        for axis_index in range(device.axis_count):
            axis = device.get_axis(axis_index + 1)
            try:
                axis.driver_enable()
            except CommandFailedException:
                self.log.exception("Failed to enable motor")
        return super().enable_motor()

    async def disable_motor(self):
        for axis_index in range(self.device.axis_count):
            axis = self.device.get_axis(axis_index + 1)
            try:
                axis.driver_disable()
            except CommandFailedException:
                self.log.exception("Failed to disable motor.")
        return super().disable_motor()

    async def update(self):
        for axis_index in range(self.device.axis_count):
            axis = self.device.get_axis(axis_index + 1)
            try:
                position = await axis.get_position_async(Units.LENGTH_MILLIMETRES)
                return position
            except CommandFailedException:
                self.log.exception("Failed to get position.")
        return super().update()

    @classmethod
    def get_config_schema(cls):
        config_schema = """
        $schema: http://json-schema.org/2020-12/schema#
        $id: https://github.com/lsst-ts/ts_LinearStage/blob/master/schema/LinearStage.yaml
        # title must end with one or more spaces followed by the schema version, which must begin with "v"
        title: Zaber v2
        description: Schema for Zaber configuration files
        type: object
        properties:
            hostname:
                type: string
            port:
                type: number
            daisy_chain_address:
                type: integer
        required:
            - hostname
            - port
            - daisy_chain_address
        additionalProperties: false
        """
        return yaml.safe_load(config_schema)


class Zaber(Stage):
    """A class representing the ZaberLST linear stage device.
    This device connected via a serial connection.

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

    commander : `zaber.serial.AsciiDevice`
        Commands the serial device.

    serial_port : `str`
        The name of the port for the device.

    address : `int`
        The address of the device along the chain.

    position : `str`
        This holds the position of the linear stage. It starts at none as
        device requires homing to be done before it can be moved.

    reply_flags : `dict`
        This is a dictionary which contains all of the reply flags
        corresponding to what they mean.

    warning_flags : `dict`
        This is a dictionary which contains all of the warning flags which
        correspond to what those flags mean.

    simulation_mode : `bool`
        Is the hardware in simulation mode.

    """

    def __init__(self, config, simulation_mode, log) -> None:
        super().__init__(config=config, simulation_mode=simulation_mode, log=log)
        self.commander = None
        self.device_address = None
        self.address = 1
        self.position = None
        self.status = None
        self.reply_flags = {
            "BADDATA": "improperly formatted or invalid data",
            "AGAIN": "The command cannot be processed right now. "
            "The user or application should send the command again.",
            "BADAXIS": "The command was sent with an axis number greater than the number of axes available.",
            "BADCOMMAND": "The command or setting is incorrect or invalid.",
            "BADMESSAGEID": "A message ID was provided, but was not either -- or a number from 0 to 99.",
            "DEVICEONLY": "An axis number was specified when trying to execute a device only command.",
            "FULL": "The device has run out of permanent storage and cannot accept the command.",
            "LOCKSTEP": "An axis cannot be moved using normal motion commands because it is part of a "
            "lockstep group.",
            "NOACCESS": "The command or setting is not available at the current access level.",
            "PARKED": "The device cannot move because it is currently parked.",
            "STATUSBUSY": "The device cannot be parked, nor can certain settings be changed, "
            "because it is currently busy.",
        }
        self.warning_flags = {
            "WR": "No reference position",
            "--": "No Warning",
            "FD": "The driver has disabled itself due to overheating.",
            "FQ": "The encoder-measured position may be unreliable. "
            "The encoder has encountered a read error due to poor sensor alignment, "
            "vibration, dirt or other environmental conditions.",
            "FS": "Stalling was detected and the axis has stopped itself.",
            "FT": "The lockstep group has exceeded allowable twist and has stopped.",
            "FB": "A previous streamed motion could not be executed because it failed a precondition "
            "(e.g. motion exceeds device bounds, calls nested too deeply).",
            "FP": "Streamed or sinusoidal motion was terminated because an axis slipped "
            "and thus the device deviated from the requested path.",
            "FE": "The target limit sensor cannot be reached or is faulty.",
            "WH": "The device has a position reference, but has not been homed. "
            "As a result, calibration has been disabled.",
            "WL": "A movement operation did not complete due to a triggered limit sensor. "
            "This flag is set if a movement operation is interrupted by a limit sensor "
            "and the No Reference Position (WR) warning flag is not present.",
            "WP": "The saved calibration data type for the specified peripheral.serial value "
            "is unsupported by the current peripheral id.",
            "WV": "The supply voltage is outside the recommended operating range of the device. "
            "Damage could result to the device if not remedied.",
            "WT": "The internal temperature of the controller has exceeded the recommended limit for the "
            "device.",
            "WM": "While not in motion, the axis has been forced out of its position.",
            "NC": "Axis is busy due to manual control via the knob.",
            "NI": "A movement operation (command or manual control) was requested "
            "while the axis was executing another movement command. "
            "This indicates that a movement command did not complete.",
            "ND": "The device has slowed down while following a streamed motion path "
            "because it has run out of queued motions.",
            "NU": "A setting is pending to be updated or a reset is pending.",
            "NJ": "Joystick calibration is in progress. Moving the joystick will have no effect.",
        }
        self.log.debug(
            f"Initialized ZaberLSTStage, simulation mode is {self.simulation_mode}"
        )

    @property
    def connected(self):
        return self.commander is not None

    async def connect(self):
        """Connect to the Stage."""
        if not self.simulation_mode:
            self.commander = zaber.AsciiDevice(
                zaber.AsciiSerial(self.config.serial_port),
                self.config.daisy_chain_address,
            )
        else:
            main, reader = pty.openpty()
            serial = zaber.AsciiSerial(os.ttyname(main))
            serial._ser = MockSerial("")
            self.commander = zaber.AsciiDevice(serial, self.config.daisy_chain_address)
        self.log.info("Connected")

    async def disconnect(self):
        """Disconnect from the stage."""
        self.commander.port.close()
        self.commander = None
        self.log.info("Disconnected from stage")

    async def enable_motor(self):
        """This method enables the motor and gets it ready to move.
        This includes transitioning the controller into the enabled/ready
        state and removing the brake (if appropriate).

        In the case of the zaberLST stage, there is no brake and it is
        always enabled

        Parameters
        ----------
        value : `bool`
            True to enable the motor, False to disable the motor.
        """
        self.log.info("Zaber stage has no brake and so this is a noop.")

    async def disable_motor(self):
        """Disable the motor.

        The Zaber motor is always enabled and so this is a noop.
        """
        self.log.info("Zaber stage has no brake and so this is a noop.")

    async def move_absolute(self, value):
        """Move the stage using absolute position. Stage must have been
         homed prior to calling this method.

        The method uses a try-catch block to handle the Timeout error
        exception.
        It sends the command which returns a reply that is logged and then
        check for accepted or rejected status according to SAL specifications.
        If the command is accepted then the command begins executing.
        The device is polled for its status until the device is idle.
        If the command finishes successfully then it is logged and the
        position is set by the get_position function.

        Parameters
        ----------
        value : `int`
            The number of millimeters(converted) to move the stage.

        Raises
        ------
        Exception
            Raised when the command is rejected
        zabar.TimeoutError
            Raised when the serial port times out.

        """

        try:
            reply = self.commander.send(
                "move abs {}".format(int(value * self.config.steps_per_mm))
            )
            self.log.info(reply)
            status_dictionary = self.check_reply(reply)
            if status_dictionary is False:
                raise salobj.ExpectedError("Command rejected")
        except zaber.TimeoutError:
            self.log.exception("Response timed out")

        # Wait 3s for stage to complete motion
        await asyncio.sleep(_ZABER_MOVEMENT_TIME)

    async def move_relative(self, value):
        """Move the stage using relative position.

        This method begins by establishing a try-catch block which handles the
        timeout exception by logging the error and proper SAL code.
        The command is then sent to the device where a reply is ostensibly
        returned.
        The reply is checked for acknowledgement or rejection and handled
        accordingly.
        If the command is accepted the device will perform the move and poll
        the device until it is idle returning SAL codes.
        The position attribute is updated using the get_position function.

        Parameters
        ----------
        value : `int`
            The number of millimeters(converted) to move the stage.

        Raises
        ------
        Exception
            Raised when command is rejected.
        zabar.TimeoutError
            Raised when serial port times out.
        """
        try:
            self.log.debug("move rel {}".format(int(value * self.config.steps_per_mm)))
            reply = self.commander.send(
                "move rel {}".format(int(value * self.config.steps_per_mm))
            )
            self.log.info(reply)
            status_dictionary = self.check_reply(reply)
            if status_dictionary is False:
                raise Exception("Command rejected")

        except zaber.TimeoutError:
            self.log.exception("Response timed out")

        # Wait 3s for stage to complete motion
        await asyncio.sleep(_ZABER_MOVEMENT_TIME)

    async def home(self):
        """Home the Zaber stage by returning to the beginning of the track.

        The method begins by forming an AsciiCommand for the home command.
        The try-catch block is then established for the rest of the method in
        order to catch the timeout error and handle it appropriately.
        The command is sent to the device and a reply is likely returned.
        The reply is then checked for accepted or rejected status.
        If the command is accepted then the command begins to perform.
        The device is polled until idle while returning the appropriate SAL
        codes.
        If the command finishes successfully then the SAL code is logged.
        """
        cmd = zaber.AsciiCommand("{} home".format(self.config.daisy_chain_address))
        try:
            reply = self.commander.send(cmd)
            self.log.info(reply)
            self.check_reply(reply)
        except zaber.TimeoutError:
            self.log.exception("Home command timed out")

        # Wait 3s for stage to complete motion
        await asyncio.sleep(_ZABER_MOVEMENT_TIME)

    def check_reply(self, reply):
        """Check the reply for any issues/

        This method has 4 if-else clauses that it checks for any normal or
        abnormal operation of the linear stage.

        Parameters
        ----------
        reply : `str`
            This is the reply that is to be checked.

        Returns
        -------
        bool
            Is the command accepted.
        """
        self.log.info(reply)
        if reply.reply_flag == "RJ" and reply.warning_flag != "--":
            self.log.warning(
                "Command rejected by device {} for {}".format(
                    self.address, self.warning_flags[reply.warning_flag]
                )
            )
            return False
        elif reply.reply_flag == "RJ" and reply.warning_flag == "--":
            self.log.error(
                "Command rejected due to {}".format(
                    self.reply_flags.get(reply.data, reply.data)
                )
            )
            return False
        elif reply.reply_flag == "OK" and reply.warning_flag != "--":
            self.log.warning(
                "Command accepted but probably would return improper result due to {}".format(
                    self.warning_flags[reply.warning_flag]
                )
            )

            return True
        else:
            self.log.info("Command accepted by device #{}".format(self.address))
            return True

    def get_position(self):
        """Return the position of the stage.

        It works by sending a command to the device and ostensibly is given a
        reply.
        The reply is then checked for acceptance or rejection by the device
        and the position is then set by the return of the reply's data if
        successful.

        Returns
        -------
        float
            The position of the stage.
        """
        try:
            reply = self.commander.send("get pos")
            self.log.info(reply)
            status_dictionary = self.check_reply(reply)
            if status_dictionary:
                self.log.info("Position captured")
                return float(float(reply.data) / self.config.steps_per_mm)
        except zaber.TimeoutError:
            self.log.exception("Position response timed out")

    def retrieve_status(self):
        """Return the status of the LinearStage.

        Returns
        -------
        str
            The status of the LinearStage.
        """
        self.log.debug("retrieve_status - starting")
        try:
            reply = self.commander.send("")
            self.log.info(reply)
            status_dictionary = self.check_reply(reply)
            if status_dictionary:
                self.log.info("retrieve_status - Status captured")
                return reply.device_status
        except zaber.TimeoutError:
            self.log.exception("Status response timed out")

    async def update(self):
        """Publish the telemetry of the stage."""
        self.position = self.get_position()
        self.status = self.retrieve_status()

    async def stop(self):
        """Stop the movement of the stage."""
        try:
            reply = self.commander.send("stop")
            self.log.debug(reply)
            status_dictionary = self.check_reply(reply)
            if status_dictionary:
                self.log.info("Device stopped")
        except zaber.TimeoutError:
            self.log.exception("Stop command response timed out")

    async def send_command(self, msg):
        self.commander.write_str(msg)
        reply = self.commander.read_str()
        status = self.check_reply(reply)
        return status

    @classmethod
    def get_config_schema(cls):
        return yaml.safe_load(
            """
        $schema: http://json-schema.org/2020-12/schema#
        $id: https://github.com/lsst-ts/ts_LinearStage/blob/master/schema/LinearStage.yaml
        # title must end with one or more spaces followed by the schema version, which must begin with "v"
        title: Zaber v1
        description: Schema for Zaber configuration files
        type: object
        properties:
            serial_port:
                type: string
            daisy_chain_address:
                type: number
            steps_per_mm:
                type: number
        required:
            - serial_port
            - daisy_chain_address
            - steps_per_mm
        additionalProperties: false
        """
        )
