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
import sys
import types

from lsst.ts import salobj, utils
from lsst.ts.xml.enums import LinearStage

from . import __version__, controllers
from .config_schema import CONFIG_SCHEMA
from .enums import ErrorCode


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
    component : `ZaberLSTStage` or `IgusLinearStageStepper`
    telemetry_task : `asyncio.Future`
    """

    valid_simulation_modes = (0, 1)
    """The valid simulation modes for the CSC."""
    version = __version__

    def __init__(
        self,
        index,
        initial_state=salobj.State.STANDBY,
        config_dir=None,
        simulation_mode=0,
        override=None,
    ):
        super().__init__(
            name="LinearStage",
            index=index,
            config_schema=CONFIG_SCHEMA,
            config_dir=config_dir,
            initial_state=initial_state,
            simulation_mode=simulation_mode,
            override=override,
        )

        self.component = None
        self.referenced = False
        self.telemetry_task = utils.make_done_future()
        self.simulation_mode_number = simulation_mode
        self.log.debug(
            f"LinearStage CSC initialized, simulation number is set to {self.simulation_mode_number}"
        )

    @staticmethod
    def get_config_pkg():
        """Return the name of the configuration package."""
        return "ts_config_mtcalsys"

    async def configure(self, config):
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
        # TODO DM-42420 Solve the dependency not being available in
        # cycle revison 2.

        # Go to fault state if dependency is not importable
        if stage_class == "ZaberV2":
            if "zaber_motion" not in sys.modules:
                await self.fault(
                    code=0,
                    report="Zaber motion library is not importable, the dependency is not installed.",
                )
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
    def detailed_state(self):
        """The substate of the LinearStage.

        Parameters
        ----------
        new_sub_state : `LinearStage.DetailedState`

        Returns
        -------
        LinearStage.DetailedState
            The current sub state of the LinearStage.
        """
        return LinearStage.DetailedState(self.evt_detailedState.data.detailedState)

    async def report_detailed_state(self, new_sub_state):
        new_sub_state = LinearStage.DetailedState(new_sub_state)
        await self.evt_detailedState.set_write(detailedState=new_sub_state)

    def assert_referenced(self, action):
        """Assert the stage is referenced.

        Parameters
        ----------
        action : `str`
            The name of the command to check.

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

    def assert_notmoving(self, action):
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
        if self.detailed_state == LinearStage.DetailedState.MOVINGSTATE:
            raise salobj.ExpectedError(
                f"DetailedState is MOVINGSTATE, {action} not allowed in state {self.detailed_state}"
            )

    def assert_target_in_range(self, target_value, move_type):
        """Is the target out of range?

        Parameters
        ----------
        target_value : `float`
            The value to move
        move_type: `str`
            The type of movement, must be "relative" or "absolute"

        Raises
        ------
        salobj.ExpectedError
            Raised when the command is not allowed in the current state.
        """
        if move_type == "relative":
            target_value = target_value + self.component.position

        if (target_value > self.target_position_maximum) or (
            target_value < self.target_position_minimum
        ):
            raise salobj.ExpectedError(
                f"Commanded {move_type} target position is not in the "
                f"permitted range of {self.target_position_minimum} to"
                f" {self.target_position_maximum} mm"
            )

    async def telemetry(self):
        """Run the telemetry loop."""
        self.log.debug(
            f"Starting telemetry loop using interval of {self.heartbeat_interval} seconds"
        )
        while True:
            try:
                await self.component.update()
                await self.tel_position.set_write(position=self.component.position)
            except Exception:
                self.log.exception("Telemetry loop failed.")
                await self.fault(
                    code=ErrorCode.TELEMETRY, report="Telemetry loop failed."
                )
            await asyncio.sleep(self.heartbeat_interval)

    async def handle_summary_state(self):
        """Handle the summary state.

        If CSC transitioning to the Disabled or Enabled state.

        * Connect to the stage if not connected.
        * Start the telemetry task if done.

        Else it will disconnect the stage and cancel the telemetry task.
        """

        if self.disabled_or_enabled:
            if not self.component.connected:
                try:
                    await self.component.connect()
                    await self.report_detailed_state(
                        LinearStage.DetailedState.NOTMOVINGSTATE
                    )
                except RuntimeError as e:
                    err_msg = "Failed to establish connection to component"
                    await self.fault(
                        code=ErrorCode.CONNECTION_FAILED, report=f"{err_msg}: {e}"
                    )
                    raise e

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
            except Exception:
                err_msg = "Failed to enable or disable motor"
                await self.fault(code=ErrorCode.DISABLE_MOTOR, report=f"{err_msg}")
        else:
            if self.component is not None:
                # component gets set when config runs, so if no component
                # is set then do nothing
                if self.component.connected:
                    await self.component.disconnect()
                    self.component = None
            self.telemetry_task.cancel()

    async def close_tasks(self):
        """End the telemetry loop and disconnect from the stage."""
        self.log.debug("Closing tasks")
        await super().close_tasks()
        self.telemetry_task.cancel()
        if self.component is not None and self.component.connected:
            await self.component.disconnect()
            self.component = None

    async def do_getHome(self, data):
        """Home the stage.

        Parameters
        ----------
        data : `cmd_getHome.DataType`
            Command data.
        """
        self.assert_enabled("getHome")
        self.assert_notmoving("getHome")
        await self.report_detailed_state(LinearStage.DetailedState.MOVINGSTATE)
        try:
            await self.component.home()
        except Exception as e:
            # reset the detailed state
            await self.report_detailed_state(LinearStage.DetailedState.NOTMOVINGSTATE)
            err_msg = "Failed to home motor"
            await self.fault(code=ErrorCode.HOME, report=f"{err_msg}: {e}")
            raise e
        self.referenced = True
        await self.report_detailed_state(LinearStage.DetailedState.NOTMOVINGSTATE)

    async def do_moveAbsolute(self, data):
        """Move the stage using absolute position.

        Parameters
        ----------
        data : `cmd_moveAbsolute.DataType`
            Command data.
        """
        self.assert_enabled("moveAbsolute")
        self.assert_notmoving("moveAbsolute")
        self.assert_referenced("moveAbsolute")
        self.assert_target_in_range(data.distance, move_type="absolute")

        await self.report_detailed_state(LinearStage.DetailedState.MOVINGSTATE)
        self.log.debug("Executing moveAbsolute")
        try:
            await self.component.move_absolute(data.distance)
        except Exception as e:
            err_msg = "Failed to perform absolute position movement"
            await self.report_detailed_state(LinearStage.DetailedState.NOTMOVINGSTATE)
            await self.fault(code=ErrorCode.MOVE_ABSOLUTE, report=f"{err_msg}: {e}")
            raise e

        await self.report_detailed_state(LinearStage.DetailedState.NOTMOVINGSTATE)
        self.log.debug("moveAbsolute complete")

    async def do_moveRelative(self, data):
        """Move the stage using relative position

        Parameters
        ----------
        data : `cmd_moveRelative.DataType`
            Command data.
        """
        self.assert_enabled("moveRelative")
        self.assert_notmoving("moveRelative")
        self.assert_target_in_range(data.distance, move_type="relative")
        await self.report_detailed_state(LinearStage.DetailedState.MOVINGSTATE)
        try:
            await self.component.move_relative(data.distance)
        except Exception:
            pass
        await self.report_detailed_state(LinearStage.DetailedState.NOTMOVINGSTATE)

    async def do_stop(self, data):
        """Stop the stage.

        Parameters
        ----------
        data : `cmd_stop.DataType`
            Command data.
        """
        self.assert_enabled("stop")
        try:
            await self.component.stop()
        except Exception:
            pass
        await self.report_detailed_state(LinearStage.DetailedState.NOTMOVINGSTATE)
