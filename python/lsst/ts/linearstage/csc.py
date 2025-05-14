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


__all__ = ["LinearStageCSC"]

import asyncio
import pathlib
import types

from lsst.ts import salobj, utils
from lsst.ts.xml.enums.LinearStage import DetailedState

# FIXME DM-45169 Remove when XML 22 is released
try:
    from lsst.ts.xml.enums.LinearStage import ErrorCode
except ImportError:
    from .enums import ErrorCode

from zaber_motion import Library, LogOutputMode

from . import __version__, controllers
from .config_schema import CONFIG_SCHEMA
from .wizardry import DEFAULT_DURATION

Library.set_log_output(LogOutputMode.STDOUT)


class LinearStageCSC(salobj.ConfigurableCsc):
    """Implements the CSC for the LinearStage.

    Parameters
    ----------
    index : `int`
        The index of the CSC.
    initial_state : `lsst.ts.salobj.State`, optional
        The initial state of the CSC.
    config_dir : `pathlib.Path`, optional
    simulation_mode : `int`, optional

    Attributes
    ----------
    component : `Stage`
    referenced : `bool`
    telemetry_task : `asyncio.Future`
    simulation_mode_number : `int`
    """

    valid_simulation_modes: tuple = (0, 1)
    """The valid simulation modes for the CSC."""
    version: str = __version__

    def __init__(
        self,
        index: int,
        initial_state: salobj.State = salobj.State.STANDBY,
        config_dir: None | pathlib.Path = None,
        simulation_mode: int = 0,
        override: None | str = None,
    ) -> None:
        super().__init__(
            name="LinearStage",
            index=index,
            config_schema=CONFIG_SCHEMA,
            config_dir=config_dir,
            initial_state=initial_state,
            simulation_mode=simulation_mode,
            override=override,
        )

        self.component: controllers.stage.Stage | None = None
        self.telemetry_task: asyncio.Future = utils.make_done_future()
        self.simulation_mode_number: int = simulation_mode
        self.log.debug(
            f"LinearStage CSC initialized, simulation number is set to {self.simulation_mode_number}"
        )

    @property
    def referenced(self) -> bool:
        if self.component is None:
            return False
        else:
            return self.component.referenced

    @staticmethod
    def get_config_pkg() -> str:
        """Return the name of the configuration package."""
        return "ts_config_mtcalsys"

    async def configure(self, config: types.SimpleNamespace) -> None:
        """Configure the CSC.

        Parameters
        ----------
        config : `types.SimpleNamespace`
        """
        for instance in config.instances:
            if self.salinfo.index == instance["sal_index"]:
                break
        if self.salinfo.index != instance["sal_index"]:
            raise RuntimeError(f"No configuration found for {self.salinfo.index=}.")
        stage_type = instance["stage_type"]
        stage_class = getattr(controllers, stage_type)
        self.validator = salobj.DefaultingValidator(stage_class.get_config_schema())
        self.target_position_minimum = instance["target_position_minimum"]
        self.target_position_maximum = instance["target_position_maximum"]
        stage_config_dict = self.validator.validate(instance["stage_config"])
        stage_config = types.SimpleNamespace(**stage_config_dict)

        # Instantiate the class specific to the hardware component
        self.component = stage_class(
            config=stage_config, simulation_mode=self.simulation_mode, log=self.log
        )

    @property
    def detailed_state(self) -> DetailedState:
        """The substate of the LinearStage.

        Parameters
        ----------
        new_sub_state : `LinearStage.DetailedState`

        Returns
        -------
        LinearStage.DetailedState
            The current sub state of the LinearStage.
        """
        return DetailedState(self.evt_detailedState.data.detailedState)

    async def report_detailed_state(self, new_sub_state: int) -> None:
        """Report the new sub state."""
        new_sub_state = DetailedState(new_sub_state)
        await self.evt_detailedState.set_write(detailedState=new_sub_state)

    def assert_referenced(self) -> None:
        """Assert the stage is referenced.

        Raises
        ------
        lsst.ts.salobj.ExpectedError
            Raised if the stage is not homed
        """
        # Stage must be homed/referenced before attempting
        # an absolute positioning
        if not self.referenced:
            raise salobj.ExpectedError(
                "Stage not homed. Perform homing prior to running this method"
            )

    def assert_notmoving(self, action: str) -> None:
        """Is the action happening while not moving.

        Parameters
        ----------
        action : `str`
            The name of the command to check.

        Raises
        ------
        salobj.ExpectedError
            Raised when the command is not allowed in the current state.
        """
        if self.detailed_state == DetailedState.MOVINGSTATE:
            raise salobj.ExpectedError(
                f"DetailedState is MOVINGSTATE, {action} not allowed in state {self.detailed_state}"
            )

    def assert_target_in_range(
        self, target_value: float, move_type: str, axis: int
    ) -> None:
        """Is the target out of range?

        Parameters
        ----------
        target_value : `float`
            The value to move
        move_type: `str`
            The type of movement, must be "relative" or "absolute"
        axis : `Axis`
            The axis to perform the command.

        Raises
        ------
        salobj.ExpectedError
            Raised when the command is not allowed in the current state.
        """
        assert self.component is not None
        if move_type == "relative":
            if (
                self.salinfo.component_info.topics["tel_position"]
                .fields["position"]
                .count
                == 1
            ):
                target_value = target_value + self.component.position[0]
            else:
                target_value = target_value + self.component.position[axis]

        if (target_value > self.target_position_maximum) or (
            target_value < self.target_position_minimum
        ):
            raise salobj.ExpectedError(
                f"Commanded {move_type} target position is not in the "
                f"permitted range of {self.target_position_minimum} to"
                f" {self.target_position_maximum} mm"
            )

    async def telemetry(self) -> None:
        """Run the telemetry loop."""
        assert self.component is not None
        self.log.debug(
            f"Starting telemetry loop using interval of {self.heartbeat_interval} seconds"
        )
        while True:
            try:
                await self.component.update()
                if (
                    self.salinfo.component_info.topics["tel_position"]
                    .fields["position"]
                    .count
                    == 1
                ):
                    await self.tel_position.set_write(
                        position=self.component.position[0]
                    )
                else:
                    await self.tel_position.set_write(position=self.component.position)
            except Exception as e:
                errmsg = "Telemetry loop failed."
                self.log.exception(errmsg)
                await self.fault(code=ErrorCode.TELEMETRY, report=f"{errmsg}: {e}")
                return
            await asyncio.sleep(self.heartbeat_interval)

    async def handle_summary_state(self) -> None:
        """Handle the summary state.

        If CSC transitioning to the Disabled or Enabled state.

        * Connect to the stage if not connected.
        * Start the telemetry task if done.

        Else it will disconnect the stage and cancel the telemetry task.
        """
        if self.disabled_or_enabled:
            assert self.component is not None
            if not self.component.connected:
                try:
                    await self.component.connect()
                    await self.report_detailed_state(DetailedState.NOTMOVINGSTATE)
                except Exception as e:
                    err_msg = "Failed to establish connection to component"
                    self.log.exception(err_msg)
                    await self.fault(
                        code=ErrorCode.CONNECTION_FAILED, report=f"{err_msg}: {e}"
                    )
                    return

            if self.telemetry_task.done():
                self.telemetry_task = asyncio.create_task(self.telemetry())
            # If enabled, then enable motor and release brake, otherwise
            # make sure it's disabled and the brake is on
            try:
                if self.summary_state == salobj.State.ENABLED:
                    self.log.debug("Enabling motor")
                    await self.component.enable_motor()
                else:
                    self.log.debug("Disabling motor")
                    await self.component.disable_motor()
            except Exception as e:
                err_msg = "Failed to enable or disable motor"
                self.log.exception(err_msg)
                await self.fault(code=ErrorCode.DISABLE_MOTOR, report=f"{err_msg}: {e}")
                raise e
        else:
            if self.component is not None:
                # component gets set when config runs, so if no component
                # is set then do nothing
                if self.component.connected:
                    await self.component.disconnect()
                    self.component = None
            self.telemetry_task.cancel()

    async def close_tasks(self) -> None:
        """End the telemetry loop and disconnect from the stage."""
        self.log.debug("Closing tasks")
        await super().close_tasks()
        self.telemetry_task.cancel()
        if self.component is not None and self.component.connected:
            await self.component.disconnect()
            self.component = None

    async def do_getHome(self, data: salobj.BaseDdsDataType) -> None:
        """Home the stage.

        Parameters
        ----------
        data : `cmd_getHome.DataType`
            Command data.
        """
        assert self.component is not None
        self.assert_enabled("getHome")
        self.assert_notmoving("getHome")
        await self.report_detailed_state(DetailedState.MOVINGSTATE)
        try:
            await self.cmd_getHome.ack_in_progress(
                data, DEFAULT_DURATION * len(self.component.axes)
            )
            await self.component.home()
        except Exception as e:
            # reset the detailed state
            await self.report_detailed_state(DetailedState.NOTMOVINGSTATE)
            err_msg = "Failed to home motor"
            await self.fault(code=ErrorCode.HOME, report=f"{err_msg}: {e}")
            raise e
        await self.report_detailed_state(DetailedState.NOTMOVINGSTATE)

    async def do_moveAbsolute(self, data: salobj.BaseDdsDataType) -> None:
        """Move the stage using absolute position.

        Parameters
        ----------
        data : `cmd_moveAbsolute.DataType`
            Command data.
        """
        assert self.component is not None
        self.assert_enabled("moveAbsolute")
        self.assert_notmoving("moveAbsolute")
        self.assert_referenced()
        self.assert_target_in_range(data.distance, move_type="absolute", axis=data.axis)

        await self.report_detailed_state(DetailedState.MOVINGSTATE)
        try:
            await self.cmd_moveAbsolute.ack_in_progress(data, DEFAULT_DURATION)
            await self.component.move_absolute(data.distance, data.axis)
        except Exception as e:
            err_msg = "Failed to perform absolute position movement"
            await self.report_detailed_state(DetailedState.NOTMOVINGSTATE)
            await self.fault(code=ErrorCode.MOVE_ABSOLUTE, report=f"{err_msg}: {e}")
            raise e
        finally:
            await self.report_detailed_state(DetailedState.NOTMOVINGSTATE)

    async def do_moveRelative(self, data: salobj.BaseDdsDataType) -> None:
        """Move the stage using relative position

        Parameters
        ----------
        data : `cmd_moveRelative.DataType`
            Command data.
        """
        assert self.component is not None
        self.assert_enabled("moveRelative")
        self.assert_notmoving("moveRelative")
        self.assert_target_in_range(data.distance, move_type="relative", axis=data.axis)
        await self.report_detailed_state(DetailedState.MOVINGSTATE)
        try:
            await self.cmd_moveRelative.ack_in_progress(data, DEFAULT_DURATION)
            await self.component.move_relative(data.distance, data.axis)
        except Exception as e:
            errmsg = "moveRelative command failed"
            await self.report_detailed_state(DetailedState.NOTMOVINGSTATE)
            await self.fault(code=ErrorCode.MOVE_RELATIVE, report=f"{errmsg}: {e}")
            raise e
        finally:
            await self.report_detailed_state(DetailedState.NOTMOVINGSTATE)

    async def do_stop(self, data: salobj.BaseDdsDataType) -> None:
        """Stop the stage.

        Parameters
        ----------
        data : `cmd_stop.DataType`
            Command data.
        """
        assert self.component is not None
        self.assert_enabled("stop")
        try:
            await self.component.stop(data.axis)
        except Exception as e:
            errmsg = "Stop failed"
            await self.report_detailed_state(DetailedState.NOTMOVINGSTATE)
            await self.fault(code=ErrorCode.STOP, report=f"{errmsg}: {e}")
            raise e
        await self.report_detailed_state(DetailedState.NOTMOVINGSTATE)
