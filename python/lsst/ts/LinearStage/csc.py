__all__ = ["LinearStageCSC"]

from lsst.ts.LinearStage.hardware import LinearStageComponent
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

    def __init__(self, index, initial_state=salobj.State.STANDBY, config_dir=None, simulation_mode=0):
        schema_path = pathlib.Path(__file__).resolve().parents[4].joinpath("schema", "LinearStage.yaml")
        super().__init__(
            name="LinearStage",
            index=index,
            schema_path=schema_path,
            config_dir=config_dir,
            initial_state=initial_state,
            simulation_mode=simulation_mode)
        self.component = LinearStageComponent(simulation_mode=bool(simulation_mode))
        self.evt_detailedState.set_put(
            detailedState=LinearStage.DetailedState(LinearStage.DetailedState.NOTMOVINGSTATE))
        self.telemetry_task = salobj.make_done_future()
        self.log.info("LinearStage CSC initialized")

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

    def allow_notmoving(self, action):
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
            raise salobj.ExpectedError(f"{action} not allowed in state {self.detailed_state}")

    async def telemetry(self):
        """Run the telemetry loop."""
        while True:
            self.component.publish()
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
                self.component.connect()
            if self.telemetry_task.done():
                self.telemetry_task = asyncio.create_task(self.telemetry())
        else:
            if self.component.connected:
                self.component.disconnect()
            self.telemetry_task.cancel()

    async def close_tasks(self):
        """End the telemetry loop and disconnect from the stage."""
        await super().close_tasks()
        self.telemetry_task.cancel()
        if self.component.connected:
            self.component.disconnect()

    async def do_getHome(self, data):
        """Home the stage.

        Parameters
        ----------
        data : `cmd_getHome.DataType`
            Command data.
        """
        self.assert_enabled("getHome")
        self.allow_notmoving("getHome")
        self.detailed_state = LinearStage.DetailedState.MOVINGSTATE
        self.component.get_home()
        await asyncio.sleep(3)
        self.detailed_state = LinearStage.DetailedState.NOTMOVINGSTATE

    async def do_moveAbsolute(self, data):
        """Move the stage using absolute position.

        Parameters
        ----------
        data : `cmd_moveAbsolute.DataType`
            Command data.
        """
        self.assert_enabled("moveAbsolute")
        self.allow_notmoving("moveAbsolute")
        self.detailed_state = LinearStage.DetailedState.MOVINGSTATE
        self.component.move_absolute(data.distance)
        await asyncio.sleep(3)
        self.detailed_state = LinearStage.DetailedState.NOTMOVINGSTATE

    async def do_moveRelative(self, data):
        """Move the stage using relative position

        Parameters
        ----------
        data : `cmd_moveRelative.DataType`
            Command data.
        """
        self.assert_enabled("moveRelative")
        self.allow_notmoving("moveRelative")
        self.detailed_state = LinearStage.DetailedState.MOVINGSTATE
        self.component.move_relative(data.distance)
        await asyncio.sleep(3)
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
