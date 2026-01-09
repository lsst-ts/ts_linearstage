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
import types
import typing

import yaml
from lsst.ts.linearstage.mocks.mock_zaber_lst import LinearStageServer
from zaber_motion import Units
from zaber_motion.ascii import Axis, AxisType, Connection, Device
from zaber_motion.exceptions import (
    CommandFailedException,
    InvalidDataException,
    RequestTimeoutException,
    MotionLibException,
)

from ..enums import Move
from ..wizardry import MAX_RETRIES
from .stage import Stage


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

    def __init__(self, config: types.SimpleNamespace, log: logging.Logger, simulation_mode: int) -> None:
        super().__init__(config, log, simulation_mode)
        self.client: Connection | None = None
        self.mock_server: LinearStageServer | None = None
        self.position: list[float] = []
        self.device: Device | None = None
        self.axes: list[Axis] = []
        self.homed: bool | None = None

    @property
    def connected(self) -> bool:
        """Is the client connected?"""
        # if client is not None check connection.is_open provided by
        # zaber-motion library.
        if self.client is not None:
            return self.client.is_open
        else:
            return False

    @property
    def referenced(self) -> bool:
        if self.homed is None:
            return False
        else:
            return self.homed

    async def _perform(self, command_name: str, axis: Axis, **kwargs: typing.Any) -> str | None:
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
        number_of_retries = 0
        result: None | str = None
        while number_of_retries <= MAX_RETRIES:
            try:
                self.log.info(f"Number {number_of_retries} of {MAX_RETRIES}")
                command = getattr(axis, command_name)
                result = await command(**kwargs)
            except CommandFailedException:
                self.log.exception(f"{command_name=} rejected for {axis=}.")
                raise
            except (RequestTimeoutException, InvalidDataException):
                self.log.exception(f"{command_name} timed out or had invalid data... Retrying.")
                number_of_retries += 1
                await asyncio.sleep(5)
            except MotionLibException as mle:
                self.log.exception(f"{command_name} had a general issue.")
                self.log.exception(f"{mle.message=}")
                for attr in ["device_addresses"]:
                    if hasattr(mle, attr):
                        self.log.exception(f"{getattr(mle, attr)}")
            else:
                return result
        return None

    async def connect(self) -> None:
        """Connect to the device."""
        if self.simulation_mode:
            self.mock_server = LinearStageServer(port=0, log=self.log, config=self.config)
            await self.mock_server.start_task
            self.config.port = self.mock_server.port
        connection_call = Connection.open_tcp_async
        kwargs = {"host_name": self.config.hostname, "port": self.config.port}
        try:
            self.client = await connection_call(**kwargs)
        except Exception:
            self.log.exception("Failed to connect to host/port.")
            raise RuntimeError(f"Unable to connect to host {self.config.hostname}.")
        if self.simulation_mode:
            self.client.checksum_enabled = False
        devices = await self.client.detect_devices_async()
        self.log.debug(f"{devices=}")
        if self.simulation_mode:
            self.device = devices[0]
        else:
            try:
                self.device = devices[self.config.daisy_chain_address - 1]
            except Exception:
                raise RuntimeError("Device is not set.")
        self.log.debug(f"{self.device=}")
        self._check_axes()
        if self.device is not None:
            self.homed = await self.device.all_axes.is_homed_async()
        self.log.debug(f"{self.homed=}")
        await self.update()

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        if self.client is not None:
            await self.client.close_async()
        self.device = None
        self.axes = []
        self.client = None

    async def move(self, move_type: Move, value: float, axis_id: int) -> None:
        """Move device to position with relative target.

        Parameters
        ----------
        move_type : `Move`
            Either relative or absolute.
        value : `float`
            The amount to move by.
        axis : `int`
            The reference to the axis to perform the command.

        Raises
        ------
        RuntimeError
            Raised when axis type is not supported.
        """
        move_type = Move(move_type)
        command_name: str = f"move_{move_type}_async"
        axis: Axis = self.axes[axis_id]
        match axis.axis_type:
            case AxisType.LINEAR:
                await self._perform(
                    command_name=command_name,
                    axis=axis,
                    position=value,
                    unit=Units.LENGTH_MILLIMETRES,
                )
            case AxisType.ROTARY:
                await self._perform(
                    command_name=command_name,
                    axis=axis,
                    position=value,
                    unit=Units.ANGLE_DEGREES,
                )
            case _:
                raise RuntimeError(f"{axis.axis_type} is not supported.")

    async def move_relative(self, value: float, axis: int) -> None:
        """Move the stage relative to the position.

        Parameters
        ----------
        value : `float`
            The value to move by.
        axis : `int`
            The axis index to use.
        """
        await self.move(move_type=Move.RELATIVE, value=value, axis_id=axis)

    async def move_absolute(self, value: float, axis: int) -> None:
        """Move the stage to the position.

        Parameters
        ----------
        value : `float`
            The target position.
        axis : `int`
            The axis ID to use.
        """
        await self.move(move_type=Move.ABSOLUTE, value=value, axis_id=axis)

    async def home(self) -> None:
        """Home the device, needed to gain awareness of position."""
        if self.device is None:
            self.homed = None
            return
        if not self.homed:
            for axis in self.axes:
                await self._perform("home_async", axis=axis)
            self.homed = await self.device.all_axes.is_homed_async()
            self.log.debug(f"{self.homed=}")
        else:
            self.log.info("No operation performed. All axes are already homed.")

    async def enable_motor(self) -> None:
        """Enable the motor to move, not supported by every model."""
        for axis in self.axes:
            await self._perform("driver_enable_async", axis=axis)

    async def disable_motor(self) -> None:
        """Disable the motor from moving, not supported on every model."""
        for axis in self.axes:
            await self._perform("driver_disable_async", axis=axis)

    async def update(self) -> None:
        """Get update of position from device.

        Raises
        ------
        RuntimeError
            Raised when axis type is not supported.
        """
        self.position = [math.nan] * len(self.axes)
        for idx, axis in enumerate(self.axes):
            self.log.debug(f"{idx=}, {axis=}")
            position_str: None | str = None
            position: None | float = None
            match axis.axis_type:
                case AxisType.LINEAR:
                    position_str = await self._perform(
                        "get_position_async", axis=axis, unit=Units.LENGTH_MILLIMETRES
                    )
                case AxisType.ROTARY:
                    position_str = await self._perform(
                        "get_position_async", axis=axis, unit=Units.ANGLE_DEGREES
                    )
                case _:
                    raise RuntimeError(f"{axis.axis_type} is not supported.")
            if position_str is not None:
                position = float(position_str)
            else:
                position = math.nan
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
            serial_number:
                type: integer
        required:
            - hostname
            - port
            - daisy_chain_address
            - stage_name
            - serial_number
        additionalProperties: false
        """
        return yaml.safe_load(config_schema)

    def _check_axes(self) -> None:
        """Get a list of axes available to use.

        Notes
        -----
        Axis addresses start at one.
        """
        if self.device is None:
            raise RuntimeError("Device is None.")
        for idx in range(1, self.device.axis_count + 1):
            axis = self.device.get_axis(idx)
            self.log.debug(f"{axis=}")
            if axis.axis_type != AxisType.UNKNOWN:
                self.axes.append(axis)
        self.log.debug(f"{self.axes=}")

    async def stop(self, axis_id: int) -> None:
        axis: Axis = self.axes[axis_id]
        await self._perform("stop_async", axis=axis)


class Zaber(ZaberV2):
    pass
