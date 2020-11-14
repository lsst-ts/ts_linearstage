__all__ = ["LinearStageCSC"]

from lsst.ts.LinearStage.controllers.igus_dryve import IgusLinearStageStepper
from lsst.ts.LinearStage.controllers.zaber_LST import ZaberLSTStage
from lsst.ts.idl.enums import LinearStage
from lsst.ts import salobj
import asyncio
import pathlib


class LinearStageCSC(salobj.ConfigurableCsc):
    """Implements the CSC for the LinearStage.

    Parameters
    ----------
    index : `int`
        The index of the CSC.
    initial_state : `salobj.State`, optional
        The initial state of the CSC.
    config_dir : `pathlib.Path`, optional
    simulation_mode : `int`, optional

    Attributes
    ----------
    component : `LinearStageComponent`
    telemetry_task : `asyncio.Future`
    """

    valid_simulation_modes = (0, 1)
    """The valid simulation modes for the CSC."""

    def __init__(
        self,
        index,
        initial_state=salobj.State.STANDBY,
        config_dir=None,
        simulation_mode=0,
    ):
        schema_path = (
            pathlib.Path(__file__)
            .resolve()
            .parents[4]
            .joinpath("schema", "LinearStage.yaml")
        )
        super().__init__(
            name="LinearStage",
            index=index,
            schema_path=schema_path,
            config_dir=config_dir,
            initial_state=initial_state,
            simulation_mode=simulation_mode,
        )

        self.evt_detailedState.set_put(
            detailedState=LinearStage.DetailedState(
                LinearStage.DetailedState.NOTMOVINGSTATE
            )
        )

        self.component = None
        self.referenced = False
        self.telemetry_task = salobj.make_done_future()
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
        self.stage_type = config.stage_type

        self.log.debug(f"Stage type is {self.stage_type}")
        self.log.debug(f"Simulation mode number is {self.simulation_mode_number}")
        # Instantiate the class specific to the hardware component
        if self.stage_type == "Igus":
            self.component = IgusLinearStageStepper(
                simulation_mode=bool(self.simulation_mode_number), log=self.log
            )
        elif self.stage_type == "Zaber":
            self.component = ZaberLSTStage(
                simulation_mode=bool(self.simulation_mode_number), log=self.log
            )

        else:
            raise IOError("Stage type not defined in config file.")

        self.component.configure(config)

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

    @detailed_state.setter
    def detailed_state(self, new_sub_state):
        new_sub_state = LinearStage.DetailedState(new_sub_state)
        self.evt_detailedState.set_put(detailedState=new_sub_state)

    def assert_referenced(self, action):
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

    async def telemetry(self):
        """Run the telemetry loop."""
        self.log.debug(
            f"Starting telemetry loop using interval of {self.heartbeat_interval} seconds"
        )
        while True:
            await self.component.publish()
            self.tel_position.set_put(position=self.component.position)
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
                except RuntimeError as e:
                    err_msg = "Failed to establish connection to component"
                    self.fault(code=2, report=f"{err_msg}: {e}")
                    raise e

            if self.telemetry_task.done():
                self.telemetry_task = asyncio.create_task(self.telemetry())
            # If enabled, then enable motor and release brake, otherwise
            # make sure it's disabled and the brake is on
            try:
                if self.summary_state == salobj.State.ENABLED:
                    self.log.debug("Enabling motor")
                    await self.component.enable_motor(True)
                else:
                    self.log.debug("Disabling motor")
                    await self.component.enable_motor(False)
            except Exception as e:
                err_msg = "Failed to enable or disable motor"
                self.fault(code=2, report=f"{err_msg}: {e}")
                raise e

        elif self.component is not None:
            # component gets set when config runs, so if no component
            # is set then do nothing
            if self.component.connected:
                await self.component.disconnect()
            self.telemetry_task.cancel()

    async def close_tasks(self):
        """End the telemetry loop and disconnect from the stage."""
        self.log.debug("Closing tasks")
        await super().close_tasks()
        self.telemetry_task.cancel()
        if self.component.connected:
            await self.component.disconnect()

    async def do_getHome(self, data):
        """Home the stage.

        Parameters
        ----------
        data : `cmd_getHome.DataType`
            Command data.
        """
        self.assert_enabled("getHome")
        self.assert_notmoving("getHome")
        self.detailed_state = LinearStage.DetailedState.MOVINGSTATE
        try:
            await self.component.get_home()
        except Exception as e:
            err_msg = "Failed to home motor"
            self.fault(code=2, report=f"{err_msg}: {e}")
            raise e
        self.referenced = True
        self.detailed_state = LinearStage.DetailedState.NOTMOVINGSTATE

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

        self.detailed_state = LinearStage.DetailedState.MOVINGSTATE
        self.log.debug("Executing moveAbsolute")
        try:
            await self.component.move_absolute(data.distance)
        except Exception as e:
            err_msg = "Failed to perform absolute position movement"
            self.detailed_state = LinearStage.DetailedState.NOTMOVINGSTATE
            self.fault(code=2, report=f"{err_msg}: {e}")
            raise e

        self.detailed_state = LinearStage.DetailedState.NOTMOVINGSTATE
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
        self.detailed_state = LinearStage.DetailedState.MOVINGSTATE
        await self.component.move_relative(data.distance)
        self.detailed_state = LinearStage.DetailedState.NOTMOVINGSTATE

    async def do_stop(self, data):
        """Stop the stage.

        Parameters
        ----------
        data : `cmd_stop.DataType`
            Command data.
        """
        self.assert_enabled("stop")
        self.component.stop()
        self.detailed_state = LinearStage.DetailedState.NOTMOVINGSTATE
