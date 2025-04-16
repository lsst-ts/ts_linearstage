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
import logging
import math
import os
import pty
import types
import typing

import yaml
from lsst.ts import salobj, tcpip
from lsst.ts.linearstage.mocks.mock_zaber_lst import LinearStageServer, MockSerial
from zaber import serial as zaber
from zaber_motion import Units
from zaber_motion.ascii import Axis, AxisType, Connection, Device
from zaber_motion.exceptions import CommandFailedException, ConnectionFailedException

from .stage import Stage

_ZABER_MOVEMENT_TIME = 3  # time to wait for zaber to complete movement/homing


class Commander:
    """Implement communication with the electrometer.

    Attributes
    ----------
    log : logging.Logger
        The log for this class.
    reader : asyncio.StreamReader
        The reader for the tcpip stream.
    writer : asyncio.StreamWriter
        The writer for the tcpip stream.
    reply_terminator : bytes
        The reply termination character.
    command_terminator : str
        The command termination character.
    lock : asyncio.Lock
        The lock for protecting reading and writing handling.
    host : str
        The hostname or ip address for the electrometer.
    port : int
        The port of the electrometer.
    timeout : int
        The amount of time to wait until a message is not received.
    connected : bool
        Whether the electrometer is connected or not.
    """

    def __init__(self, log: None | logging.Logger = None) -> None:
        # Create a logger if none were passed during the instantiation of
        # the class
        self.log: None | logging.Logger = None
        if log is None:
            self.log = logging.getLogger(type(self).__name__)
        else:
            self.log = log.getChild(type(self).__name__)

        self.reader: None = None
        self.writer: None = None
        self.reply_terminator: bytes = b"\r"
        self.command_terminator: str = "\r"
        self.lock: asyncio.Lock = asyncio.Lock()
        self.host: str = tcpip.LOCAL_HOST
        self.port: int = 9999
        self.timeout: int = 5
        self.long_timeout: int = 30
        self.connected: bool = False
        self.moxa: bool = False

    async def connect(self) -> None:
        """Connect to the electrometer"""

        if not self.simulation_mode:
            if self.moxa:
                async with self.lock:
                    try:
                        connect_task = asyncio.open_connection(
                            host=self.host, port=int(self.port), limit=1024 * 1024 * 10
                        )
                        self.reader, self.writer = await asyncio.wait_for(
                            connect_task, timeout=self.long_timeout
                        )
                    except Exception as e:
                        raise RuntimeError(
                            f"Failed to connect. {self.host=} {self.port=}: {e!r}"
                        )
            else:
                self.device = zaber.AsciiDevice(
                    zaber.AsciiSerial(self.config.serial_port),
                    self.config.daisy_chain_address,
                )
            self.connected = True

        else:
            main, reader = pty.openpty()
            serial = zaber.AsciiSerial(os.ttyname(main))
            serial._ser = MockSerial("")
            self.device = zaber.AsciiDevice(serial, self.config.daisy_chain_address)

        self.log.info("Connected")

    async def disconnect(self) -> None:
        """Disconnect from the electrometer."""
        if self.moxa:
            async with self.lock:
                if self.writer is None:
                    return
                try:
                    await tcpip.close_stream_writer(self.writer)
                except Exception:
                    self.log.exception("Disconnect failed, continuing")
                finally:
                    self.device = None
                    self.writer = None
                    self.reader = None
                    self.connected = False
        else:
            try:
                self.device.port.close()
                self.device = None
                self.log.info("Disconnected from stage")
            except Exception:
                self.log.exception("Disconnect failed, continuing")
            finally:
                self.device = None
                self.write = None
                self.reader = None
                self.connected = False

    async def send(
        self, msg: str, has_reply: bool = False, timeout: typing.Optional[int] = None
    ) -> str:
        """Send a command to the electrometer and read reply if has one.

        Parameters
        ----------
        msg : `str`
            The message to send.
        has_reply : `bool`
            Does the command expect a reply.

        Returns
        -------
        reply
        """
        if timeout is None:
            self.log.debug(f"Will use timeout {self.timeout}s")
        else:
            self.log.debug(f"Will use timeout {timeout}s")

        if self.moxa:
            async with self.lock:
                msg = (
                    f"/{self.config.daisy_chain_address}"
                    + msg
                    + self.command_terminator
                )
                msg = msg.encode("ascii")
                if self.writer is not None:
                    self.log.debug(f"Commanding using: {msg}")
                    self.writer.write(msg)
                    await self.writer.drain()
                    if has_reply:
                        reply = await asyncio.wait_for(
                            self.reader.readuntil(self.reply_terminator),
                            timeout=self.timeout if timeout is None else timeout,
                        )
                        self.log.debug(f"reply={reply}")
                        reply = reply.decode("ascii").strip()
                        return reply
                    return None
                else:
                    raise RuntimeError("CSC not connected.")
        else:
            try:
                reply = self.device.send(
                    "move abs {}".format(int(msg * self.config.steps_per_mm))
                )
                self.log.info(reply)
                status_dictionary = self.check_reply(reply)
                if status_dictionary is False:
                    raise Exception("Command rejected")
            except zaber.TimeoutError:
                self.log.exception("Response timed out")


class ZaberV2(Stage):
    """Implement Zaber stage with zaber-motion library.

    Parameters
    ----------
    config : `types.Simplenamespace`
        The controller specific schema.
    log : `logging.Logger`
        The log of the controller.
    simulation_mode:
        Is the controller in simulation mode?

    Attributes
    ----------
    client : `None` | `tcpip.Client`
        The tcpip client that commands the device.
    mock_server : `None` | `LinearStageServer`
        The mock server that's started if in simulation mode.
    position : `None` | `float`
        The position of the stage along the axis.

    """

    def __init__(
        self, config: types.SimpleNamespace, log: logging.Logger, simulation_mode: int
    ) -> None:
        super().__init__(config, log, simulation_mode)
        self.client: Connection | None = None
        self.mock_server: LinearStageServer | None = None
        self.position: list[float] = []
        self.device: Device | None = None
        self.axes: list[Axis] = []

    @property
    def connected(self) -> bool:
        """Is the client connected?"""
        # if client is not None assume connected since zaber=motion
        # does not provide check for connection status.
        if self.client is not None:
            return True
        else:
            return False

    @property
    def referenced(self):
        return self.device.all_axes.is_homed()

    async def _perform(self, command_name: str, axis: Axis, **kwargs: typing.Any):
        """Send a command to the axis.

        Parameters
        ----------
        command_name : `str`
            Name of the method to call.
        axis : `Axis`
            The axis to perform the command.
        kwargs : `typing.Any`
            kwargs for the command.

        Raises
        ------
        RuntimeError
            Raised when device is none.
        CommandFailedException
            Raised when a command is rejected by the axis.
        """
        if self.device is None:
            raise RuntimeError("Device has not been received.")
        try:
            command = getattr(axis, command_name)
            return await command(**kwargs)
        except CommandFailedException:
            self.log.exception(f"{command_name=} rejected for {axis=}.")
            raise

    async def connect(self) -> None:
        """Connect to the device."""
        if self.simulation_mode:
            self.mock_server = LinearStageServer(port=0, log=self.log)
            await self.mock_server.start_task
            self.config.port = self.mock_server.port
        try:
            self.client = await Connection.open_tcp_async(
                host_name=self.config.hostname, port=self.config.port
            )
        except ConnectionFailedException:
            self.log.exception("Failed to connect to host/port.")
            raise RuntimeError(f"Unable to connect to host {self.config.hostname}.")
        devices = await self.client.detect_devices_async()
        self.device = devices[self.config.daisy_chain_address]
        self.log.debug(f"{self.device=}")
        self._check_axes()
        await self.update()

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        if self.client is not None:
            await self.client.close_async()
        self.device = None
        self.axes = []
        self.client = None
        if self.simulation_mode:
            if self.mock_server is not None:
                await self.mock_server.close()
            self.mock_server = None

    async def move_relative(self, value: float, axis: Axis) -> None:
        """Move device to position with relative target.

        Parameters
        ----------
        value : `float`
            The amount to move by.
        axis : `Axis`
            The axis to perform the command.
        """
        axis: Axis = self.axes[axis]
        match axis.axis_type:
            case AxisType.LINEAR:
                await self._perform(
                    "move_relative_async",
                    axis=axis,
                    position=value,
                    unit=Units.LENGTH_MILLIMETRES,
                )
            case AxisType.ROTARY:
                await self._perform(
                    "move_relative_absolute",
                    axis=axis,
                    position=value,
                    units=Units.ANGLE_DEGREES,
                )
            case _:
                raise RuntimeError(f"{axis.axis_type} is not supported.")

    async def move_absolute(self, value: float, axis: Axis) -> None:
        """Move the device to value.

        Parameters
        ----------
        value : `float`
            The position to move to.
        axis : `Axis`
            The axis to perform the command.
        """
        axis: Axis = self.axes[axis]
        match axis.axis_type:
            case AxisType.LINEAR:
                await self._perform(
                    "move_absolute_async",
                    axis=axis,
                    position=value,
                    unit=Units.LENGTH_MILLIMETRES,
                )
            case AxisType.ROTARY:
                await self._perform(
                    "move_absolute_async",
                    axis=axis,
                    position=value,
                    unit=Units.ANGLE_DEGREES,
                )
            case _:
                raise RuntimeError(f"{axis.axis_type} is not supported.")

    async def home(self) -> None:
        """Home the device, needed to gain awareness of position."""
        for axis in self.axes:
            await self._perform("home_async", axis=axis)

    async def enable_motor(self) -> None:
        """Enable the motor to move, not supported by every model."""
        for axis in self.axes:
            await self._perform("driver_enable_async", axis=axis)

    async def disable_motor(self) -> None:
        """Disable the motor from moving, not supported on every model."""
        for axis in self.axes:
            await self._perform("driver_disable_async", axis=axis)

    async def update(self) -> None:
        """Get update of position from device."""
        self.position = [math.nan] * len(self.axes)
        for idx, axis in enumerate(self.axes):
            self.log.debug(f"{idx=}, {axis=}")
            match axis.axis_type:
                case AxisType.LINEAR:
                    position = await self._perform(
                        "get_position_async", axis=axis, unit=Units.LENGTH_MILLIMETRES
                    )
                case AxisType.ROTARY:
                    position = await self._perform(
                        "get_position_async", axis=axis, unit=Units.ANGLE_DEGREES
                    )
                case _:
                    raise RuntimeError(f"{axis.axis_type} is not supported.")
            self.position[idx] = position

    @classmethod
    def get_config_schema(cls) -> dict:
        """Get the device specific config schema."""
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
            stage_name:
                type: string
        required:
            - hostname
            - port
            - daisy_chain_address
            - stage_name
        additionalProperties: false
        """
        return yaml.safe_load(config_schema)

    def _check_axes(self):
        """Get a list of axes available to use.

        Notes
        -----
        Axis addresses start at one.
        """
        for idx in range(1, self.device.axis_count + 1):
            axis = self.device.get_axis(idx)
            self.log.debug(f"{axis=}")
            if axis.axis_type != AxisType.UNKNOWN:
                self.axes.append(axis)
        self.log.debug(f"{self.axes=}")


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
        """Is the client connected?"""
        return self.commander is not None

    async def connect(self):
        """Connect to the Stage."""
        self.commander = Commander()
        self.commander.connect()

        self.log.info("Connected")

    async def disconnect(self):
        """Disconnect from the stage."""
        self.commander.disconnect()
        self.commander = None
        self.log.info("Disconnected from stage")

    async def enable_motor(self):
        """This method enables the motor and gets it ready to move.
        This includes transitioning the controller into the enabled/ready
        state and removing the brake (if appropriate).

        In the case of the zaberLST stage, there is no brake and it is
        always enabled
        """
        pass

    async def disable_motor(self):
        """Disable the motor.

        The Zaber motor is always enabled and so this is a noop.
        """
        pass

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
        f"move abs {int(value * self.config.steps_per_mm)}"

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
        f"move rel {int(value * self.config.steps_per_mm)}"

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
        cmd = "home"

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
        "get pos"
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
        """Send a command and check the reply for status.

        Parameters
        ----------
        msg : `str`
            The message to be sent.
        """
        self.commander.write_str(msg)
        reply = self.commander.read_str()
        status = self.check_reply(reply)
        return status

    @classmethod
    def get_config_schema(cls):
        """Get the device specific schema."""
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
