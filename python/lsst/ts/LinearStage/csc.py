__all__ = ["LinearStageCSC"]

from lsst.ts.LinearStage.hardware import ZaberLSTStage
from lsst.ts.idl.enums import LinearStage
from lsst.ts import salobj
import asyncio
import pathlib


class LinearStageCSC(salobj.ConfigurableCsc):
    valid_simulation_modes = [0]

    def __init__(self, index, initial_state=salobj.State.STANDBY, config_dir=None, simulation_mode=0):
        schema_path = pathlib.Path(__file__).resolve().parents[4].joinpath("schema", "LinearStage.yaml")
        super().__init__(
            name="LinearStage",
            index=index,
            schema_path=schema_path,
            config_dir=config_dir,
            initial_state=initial_state,
            simulation_mode=simulation_mode)
        self.component = ZaberLSTStage()
        self.evt_detailedState.set_put(
            detailedState=LinearStage.DetailedState(LinearStage.DetailedState.NOTMOVINGSTATE))
        self.telemetry_task = salobj.make_done_future()

    @staticmethod
    def get_config_pkg():
        return "ts_config_mtcalsys"

    async def configure(self, config):
        self.component.configure(config)

    @property
    def detailed_state(self):
        return LinearStage.DetailedState(self.evt_detailedState.data.detailedState)

    @detailed_state.setter
    def detailed_state(self, new_sub_state):
        new_sub_state = LinearStage.DetailedState(new_sub_state)
        self.evt_detailedState.set_put(detailedState=new_sub_state)

    def allow_notmoving(self, action):
        if self.detailed_state == LinearStage.DetailedState.MOVINGSTATE:
            raise salobj.ExpectedError(f"{action} not allowed in state {self.detailed_state}")

    async def telemetry(self):
        while True:
            self.component.publish()
            self.tel_position.set_put(position=self.component.position)
            await asyncio.sleep(self.heartbeat_interval)

    async def handle_summary_state(self):
        if self.disabled_or_enabled:
            if not self.component.connected:
                self.component.connect()
            if self.telemetry_task.done():
                self.telemetry_task = asyncio.create_task(self.telemetry())
        else:
            if self.component.connected:
                self.component.disconnect()
            self.telemetry_task.cancel()

    async def do_getHome(self, data):
        self.assert_enabled("getHome")
        self.allow_notmoving("getHome")
        self.detailed_state = LinearStage.DetailedState.MOVINGSTATE
        self.component.get_home()
        await asyncio.sleep(3)
        self.detailed_state = LinearStage.DetailedState.NOTMOVINGSTATE

    async def do_moveAbsolute(self, data):
        self.assert_enabled("moveAbsolute")
        self.allow_notmoving("moveAbsolute")
        self.detailed_state = LinearStage.DetailedState.MOVINGSTATE
        self.component.move_absolute(data.distance)
        await asyncio.sleep(3)
        self.detailed_state = LinearStage.DetailedState.NOTMOVINGSTATE

    async def do_moveRelative(self, data):
        self.assert_enabled("moveRelative")
        self.allow_notmoving("moveRelative")
        self.detailed_state = LinearStage.DetailedState.MOVINGSTATE
        self.component.move_relative(data.distance)
        await asyncio.sleep(3)
        self.detailed_state = LinearStage.DetailedState.NOTMOVINGSTATE

    async def do_stop(self, data):
        self.assert_enabled("stop")
        self.component.stop()
        self.detailed_state = LinearStage.DetailedState.NOTMOVINGSTATE
