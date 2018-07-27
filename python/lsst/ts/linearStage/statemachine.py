from lsst.ts.statemachine.states import EnabledState, DisabledState, StandbyState, FaultState, OfflineState, \
    DefaultState
from lsst.ts.statemachine.context import Context
from .ls import LinearStageComponent
from salpytools import salpylib


class DisabledState(DisabledState):
    def __init__(self):
        super(DisabledState, self).__init__('DISABLED', 'linearStage')

    def do(self, model):
        pass

    def enable(self, model):
        model.enable()
        model.change_state("ENABLED")
        return (0, 'Done')

    def exit(self, model):
        pass


class EnabledState(EnabledState):
    def __init__(self):
        super(EnabledState, self).__init__('ENABLED', 'linearStage')

    def do(self, model):
        pass

    def disable(self, model):
        model.disable()
        model.change_state('DISABLED')
        return (0, 'Done')

    def exit(self, model):
        pass

    def home(self, model):
        code, message = model.home()
        return (code,message)

    def move_absolute(self, model):
        code, message = model.move_absolute(self.data.distance)
        return (code, message)

    def move_relative(self, model):
        code, message = model.move_relative(self.data.distance)
        return (code, message)

    def get_position(self, model):
        code, message = model.get_position()
        return (code, message)


class StandbyState(StandbyState):
    def __init__(self):
        super(StandbyState, self).__init__('STANDBY', 'linearStage')

    def do(self, model):
        model.start()
        model.change_state("DISABLED")
        return (0, 'Done')

    def exit(self, model):
        pass


class FaultState(FaultState):
    def __init__(self):
        super(FaultState, self).__init__('FAULT', 'linearStage')

    def do(self, model):
        pass


class OfflineState(OfflineState):
    def __init__(self):
        super(OfflineState, self).__init__('OFFLINE', 'linearStage')

    def do(self, model):
        pass

    def enter_control(self, model):
        model.change_state("STANDBY")
        return (0, 'Done')

    def exit(self, model):
        pass


class LinearStageModel:
    def __init__(self, port, address):
        self.state = "OFFLINE"
        self.previous_state = None
        self._ls = None
        self._port = port
        self._address = address
        self._dds = salpylib.DDSSend('linearStage')
        self._ss_dict = {"OFFLINE": 5, "STANDBY": 4, "DISABLED": 1, "ENABLED": 2, "FAULT": 3}

    def change_state(self, state):
        self.previous_state = self.state
        self.state = state
        self._dds.send_Event('SummaryState', summaryState=self._ss_dict[state])

    def start(self):
        self._ls = LinearStageComponent(port=self._port, address=self._address)

    def enable(self):
        self._ls.enable()

    def disable(self):
        self._ls.disable()

    def home(self):
        code, message = self._ls.get_home()
        self._dds.send_Event('getHome')
        return code, message

    def move_absolute(self, distance):
        code, message = self._ls.move_absolute(distance)
        self._dds.send_Event('moveAbsolute')
        return code, message

    def move_relative(self, distance):
        code, message = self._ls.move_relative(distance)
        self._dds.send_Event('moveRelative')
        return code, message

    def get_position(self):
        position = self._ls.get_position()
        self._dds.send_Event('getPosition')
        self._dds.send_Telemetry('position', position=position)


class LinearStageCSC:
    def __init__(self, port, address):
        self.model = LinearStageModel(port=port, address=address)
        self.subsystem_tag = 'linearStage'
        self.states = {"OFFLINE": OfflineState(), "STANDBY": StandbyState(), "DISABLED": DisabledState(),
                       "ENABLED": EnabledState(), "FAULT": FaultState()}

        self.context = Context(subsystem_tag=self.subsystem_tag, model=self.model, states=self.states)
        self.context.add_command('getHome', 'home')
        self.context.add_command('moveAbsolute', 'move_absolute')
        self.context.add_command('moveRelative', 'move_relative')
        self.context.add_command('getPosition', 'get_position')
        self.entercontrol = salpylib.DDSController(context=self.context, command='enterControl')
        self.start = salpylib.DDSController(context=self.context, command='start')
        self.enable = salpylib.DDSController(context=self.context, command='enable')
        self.disable = salpylib.DDSController(context=self.context, command='disable')
        self.exitcontrol = salpylib.DDSController(context=self.context, command='exitControl')
        self.home = salpylib.DDSController(context=self.context, command='getHome')
        self.moveabsolute = salpylib.DDSController(context=self.context, command='moveAbsolute')
        self.moverelative = salpylib.DDSController(context=self.context, command='moveRelative')
        self.getposition = salpylib.DDSController(context=self.context, command='getPosition')

        self.entercontrol.start()
        self.start.start()
        self.enable.start()
        self.disable.start()
        self.exitcontrol.start()
        self.home.start()
        self.moveabsolute.start()
        self.moverelative.start()
        self.getposition.start()
