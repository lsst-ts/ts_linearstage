from time import sleep

from lsst.ts.statemachine.states import EnabledState, DisabledState, StandbyState, FaultState, OfflineState, \
    DefaultState
from lsst.ts.statemachine.context import Context
from .ls import LinearStageComponent
from salpytools import salpylib
import logging
logger = logging.getLogger(__name__)


class DisabledState(DisabledState):
    def __init__(self):
        super(DisabledState, self).__init__('DISABLED', 'LinearStage')

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
        super(EnabledState, self).__init__('ENABLED', 'LinearStage')

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
        code, message , position = model.get_position()
        return (code, message, position)


class MovingState(DefaultState):
    def __init__(self):
        super(MovingState, self).__init__('MOVING', 'LinearStage')

    def do(self, model):
        model.change_state("ENABLED")

    def stop(self, model):
        code, message = model.stop()
        return code, message


class StandbyState(StandbyState):
    def __init__(self):
        super(StandbyState, self).__init__('STANDBY', 'LinearStage')

    def do(self, model):
        pass

    def exit(self, model):
        pass


class FaultState(FaultState):
    def __init__(self):
        super(FaultState, self).__init__('FAULT', 'LinearStage')

    def do(self, model):
        pass


class OfflineState(OfflineState):
    def __init__(self):
        super(OfflineState, self).__init__('OFFLINE', 'LinearStage')

    def do(self, model):
        pass

    def enter_control(self, model):
        model.start()
        model.home()
        model.change_state("STANDBY")
        return (0, 'Done')

    def exit(self, model):
        pass


class LinearStageModel:
    def __init__(self, port, address):
        self._ls = None
        self._port = port
        self._address = address
        self._dds = salpylib.DDSSend('LinearStage',device_id=self._address)
        self._ss_dict = {"OFFLINE": 5, "STANDBY": 4, "DISABLED": 1, "ENABLED": 2, "FAULT": 3, "MOVING": 2}
        self._ds_dict = {"OFFLINE": 5, "STANDBY": 4, "DISABLED": 1, "ENABLED": 2, "FAULT": 3, "MOVING": 6}
        self.state = "OFFLINE"
        self.previous_state = None
        self.status = None
        self.frequency = 0.05
        self.position = None
        self.status = None

    def change_state(self, state):
        logger.debug(self.state)
        self.previous_state = self.state
        self.state = state
        self._dds.send_Event('summaryState', summaryState=self._ss_dict[state])
        self._dds.send_Event('detailedState', detailedState=self._ds_dict[state])
        logger.debug(self.state)

    def start(self):
        self._ls = LinearStageComponent(port=self._port, address=self._address)

    def enable(self):
        self._ls.enable()

    def disable(self):
        self._ls.disable()

    def home(self):
        code, message = self._ls.get_home()
        logger.debug(self.state)
        self.change_state("MOVING")
        logger.debug(self.state)
        while self.retrieve_status()[0] != "IDLE":
            self.position = self.get_position()
            sleep(self.frequency)
        self._dds.send_Event('getHome',)
        return code, message

    def move_absolute(self, distance):
        code, message = self._ls.move_absolute(distance)
        self.change_state("MOVING")
        while self._ls.get_status() != "IDLE":
            self.position = self.get_position()
            sleep(self.frequency)
        self._dds.send_Event('moveAbsolute')
        return code, message

    def move_relative(self, distance):
        code, message = self._ls.move_relative(distance)
        self.change_state("MOVING")
        while self.retrieve_status()[0] != "IDLE":
            self.position = self.get_position()
            sleep(self.frequency)
        self._dds.send_Event('moveRelative')
        return code, message

    def get_position(self):
        position, code, message = self._ls.get_position()
        self._dds.send_Event('getPosition')
        self._dds.send_Telemetry('position', position=position)
        return position, code, message

    def retrieve_status(self):
        status, code, message = self._ls.retrieve_status()
        self.status = status
        return status, code, message

    def stop(self):
        code, message = self._ls.stop()
        self._dds.send_Event("stop")
        return code, message

    def set_speed(self, speed):
        code, message = self._ls.set_speed(speed)
        self._dds.send_Event('setSpeed')
        return code, message


class LinearStageCSC:
    def __init__(self, port, address):
        self.model = LinearStageModel(port=port, address=address)
        self.subsystem_tag = 'LinearStage'
        self.states = {"OFFLINE": OfflineState(), "STANDBY": StandbyState(), "DISABLED": DisabledState(),
                       "ENABLED": EnabledState(), "FAULT": FaultState(), "MOVING": MovingState()}

        self.context = Context(subsystem_tag=self.subsystem_tag, model=self.model, states=self.states)
        self.context.add_command('getHome', 'home')
        self.context.add_command('moveAbsolute', 'move_absolute')
        self.context.add_command('moveRelative', 'move_relative')
        self.context.add_command('getPosition', 'get_position')
        self.context.add_command('stop', 'stop')
        self.entercontrol = salpylib.DDSController(context=self.context, command='enterControl',
                                                   device_id=address)
        self.start = salpylib.DDSController(context=self.context, command='start',
                                            device_id=address)
        self.enable = salpylib.DDSController(context=self.context, command='enable',
                                             device_id=address)
        self.disable = salpylib.DDSController(context=self.context, command='disable',
                                              device_id=address)
        self.exitcontrol = salpylib.DDSController(context=self.context, command='exitControl',
                                                  device_id=address)
        self.standby = salpylib.DDSController(context=self.context, command='standby',
                                              device_id=address)
        self.home = salpylib.DDSController(context=self.context, command='getHome',
                                           device_id=address)
        self.moveabsolute = salpylib.DDSController(context=self.context, command='moveAbsolute',
                                                   device_id=address)
        self.moverelative = salpylib.DDSController(context=self.context, command='moveRelative',
                                                   device_id=address)
        self.getposition = salpylib.DDSController(context=self.context, command='getPosition',
                                                  device_id=address)
        self.stop = salpylib.DDSController(context=self.context, command='stop',
                                           device_id=address)

    def run(self):
        self.entercontrol.start()
        self.start.start()
        self.enable.start()
        self.disable.start()
        self.exitcontrol.start()
        self.standby.start()
        self.home.start()
        self.moveabsolute.start()
        self.moverelative.start()
        self.getposition.start()
        self.stop.start()
        logger.info('Component ready...')

    def stop_csc(self, signum, frame):
        logger.info('Received signal %s [%s]... Stopping components...', signum, frame)
        self.entercontrol.stop()
        self.start.stop()
        self.enable.stop()
        self.disable.stop()
        self.exitcontrol.stop()
        self.standby.stop()
        self.home.stop()
        self.moveabsolute.stop()
        self.moverelative.stop()
        self.getposition.stop()
        self.stop.stop()
        logger.info('Waiting for threads to finish...')
        self.entercontrol.join()
        self.start.join()
        self.enable.join()
        self.disable.join()
        self.exitcontrol.join()
        self.home.join()
        self.moveabsolute.join()
        self.moverelative.join()
        self.getposition.join()
        self.stop.join()
        logger.info('Done')
