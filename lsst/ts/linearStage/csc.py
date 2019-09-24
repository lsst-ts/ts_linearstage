from lsst.ts.linearStage.hardware import LinearStageComponent
from lsst.ts import salobj
import asyncio
import enum


class LinearStageDetailedState(enum.IntEnum):
    DISABLEDSTATE = 1
    ENABLEDSTATE = 2
    FAULTSTATE = 3
    OFFLINESTATE = 4
    STANDBYSTATE = 5
    MOVINGSTATE = 6


class LinearStageCSC(salobj.BaseCsc):
    def __init__(self, port, address, index, initial_state=salobj.State.STANDBY, frequency=1):
        super().__init__("LinearStage", index=index, initial_state=initial_state)
        self.model = LinearStageModel(port, address)
        self.frequency = frequency
        self.position_topic = self.tel_position.DataType()
        self._detailed_state = LinearStageDetailedState(initial_state)

    @property
    def detailed_state(self):
        return self._detailed_state

    @detailed_state.setter
    def detailed_state(self, new_sub_state):
        self._detailed_state = LinearStageDetailedState(new_sub_state)
        detailed_state_topic = self.evt_detailedState.DataType()
        detailed_state_topic.detailedState = self._detailed_state
        self.evt_detailedState.put(detailed_state_topic)

    def allow_notmoving(self, action):
        if self.detailed_state == LinearStageDetailedState.MOVINGSTATE:
            raise salobj.ExpectedError(f"{action} not allowed in state {self.detailed_state}")

    async def telemetry(self):
        while True:
            self.model.publish()
            self.position_topic.position = self.model.position
            self.tel_position.put(self.position_topic)
            await asyncio.sleep(self.frequency)

    async def begin_enable(self):
        self.model._ls.enable()
        asyncio.ensure_future(self.telemetry())

    async def begin_disable(self):
        self.model._ls.disable()
        self.telemetry.cancel

    async def do_getHome(self, id_data):
        self.assert_enabled("getHome")
        self.allow_notmoving("getHome")
        self.detailed_state = LinearStageDetailedState.MOVINGSTATE
        self.model.get_home()
        await asyncio.sleep(3)
        self.detailed_state = LinearStageDetailedState.ENABLEDSTATE

    async def do_moveAbsolute(self, id_data):
        self.assert_enabled("moveAbsolute")
        self.allow_notmoving("moveAbsolute")
        self.detailed_state = LinearStageDetailedState.MOVINGSTATE
        self.model.move_absolute(id_data.data.distance)
        await asyncio.sleep(3)
        self.detailed_state = LinearStageDetailedState.ENABLEDSTATE

    async def do_moveRelative(self, id_data):
        self.assert_enabled("moveRelative")
        self.allow_notmoving("moveRelative")
        self.detailed_state = LinearStageDetailedState.MOVINGSTATE
        self.model.move_relative(id_data.data.distance)
        await asyncio.sleep(3)
        self.detailed_state = LinearStageDetailedState.ENABLEDSTATE

    async def do_stop(self, id_data):
        self.assert_enabled("stop")
        self.model.stop()
        self.detailed_state = LinearStageDetailedState.ENABLEDSTATE


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
