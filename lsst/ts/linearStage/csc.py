from lsst.ts.linearStage.hardware import LinearStageComponent
from lsst.ts.salobj import *
import SALPY_LinearStage
import asyncio


class LinearStageCSC(BaseCsc):
    def __init__(self, port, address, initial_state=State.STANDBY, frequency=1):
        super().__init__(SALPY_LinearStage)
        self.model = LinearStageModel(port, address)
        self.summary_state = initial_state
        self.frequency = frequency
        self.position_topic = self.tel_position.DataType()
        self.detailed_state = 0
        asyncio.ensure_future(self.telemetry())

    @property
    def detailed_state(self):
        detailed_state_topic = self.evt_detailedState.DataType()
        return detailed_state_topic.detailedState

    @detailed_state.setter
    def detailed_state(self, new_sub_state):
        detailed_state_topic = self.evt_detailedState.DataType()
        detailed_state_topic.detailedState = new_sub_state
        self.evt_detailedState.put(detailed_state_topic)

    def assert_notmoving(self, action):
        if self.detailed_state == 1:
            raise ExpectedError(f"{action} not allowed in state {self.detailed_state}")

    def assert_moving(self,action):
        if self.detailed_state != 1:
            raise ExpectedError(f"{action} not allowed in state {self.detailed_state}")

    async def telemetry(self):
        while True:
            self.model.publish()
            self.position_topic.position = self.model.position
            self.tel_position.put(self.position_topic)
            await asyncio.sleep(self.frequency)

    async def do_getHome(self, id_data):
        self.assert_enabled("getHome")
        self.assert_notmoving("getHome")
        self.detailed_state = 1
        self.model.get_home()
        await self.wait_idle()
        self.detailed_state = 0

    async def wait_idle(self):
        if self.model.status != "IDLE":
            asyncio.sleep(self.frequency)

    async def do_moveAbsolute(self, id_data):
        self.assert_enabled("moveAbsolute")
        self.assert_notmoving("moveAbsolute")
        self.detailed_state = 1
        self.model.move_absolute(id_data.data.position)
        await self.wait_idle()
        self.detailed_state = 0

    async def do_moveRelative(self, id_data):
        self.assert_enabled("moveRelative")
        self.assert_notmoving("moveRelative")
        self.detailed_state = 1
        self.model.move_relative(id_data.data.position)
        await self.wait_idle()

    async def do_stop(self, id_data):
        self.assert_enabled("stop")
        self.assert_moving("stop")
        self.model.stop()
        await self.wait_idle()
        self.detailed_state = 0


class LinearStageModel:
    def __init__(self, port, address):
        self._ls = LinearStageComponent(port, address)
        self.position = None
        self.status = None

    def get_home(self):
        self._ls.get_home()

    def move_absolute(self, position):
        self._ls.move_absolute(position)

    def move_relative(self, position):
        self._ls.move_relative(position)

    def stop(self):
        self._ls.stop()

    def publish(self):
        self.position = self._ls.get_position()
        self.status = self._ls.get_status()
