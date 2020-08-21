from lewis.devices import StateMachineDevice

from lewis.core.statemachine import State
from lewis.core import approaches

from collections import OrderedDict

from lewis.adapters.stream import StreamInterface, Cmd, scanf


class DefaultMovingState(State):
    def in_state(self, dt):
        old_position = self._context.position
        self._context.position = approaches.linear(old_position, self._context.target, self._context.speed, dt)
        self.log.info(f"Moved position ({old_position} -> {self._context.position}), target={self._context.target}, speed={self._context.speed}")


class SimulatedLinearStage(StateMachineDevice):
    def _initialize_data(self):
        self.position = 0
        self._target = 0
        self.speed = 2000
        self.homed = False

    def _get_state_handlers(self):
        return {
            'idle': State(),
            'busy': DefaultMovingState()
        }

    def _get_initial_state(self):
        return 'idle'

    def _get_transition_handlers(self):
        return OrderedDict([
            (('idle', 'busy'), lambda: self.position != self.target),
            (('busy', 'idle'), lambda: self.position == self.target)
        ])

    @property
    def state(self):
        return self._csm.state

    @property
    def target(self):
        return self._target

    @target.setter
    def target(self, new_target):
        self._target = new_target

    def stop(self):
        self._target = self.position
        self.log.info("Stopping movement after user's request.")


class ExampleLinearStageStreamInterface(StreamInterface):
    commands =  {
        Cmd('get_status', r"^/1 1$"),
        Cmd('get_position', r"^/1 1 get pos$"),
        Cmd('move_relative', scanf("/1 1 move rel %d"), argument_mappings=(int,)),
        Cmd("move_absolute", scanf("/1 1 move abs %d"), argument_mappings=(int,)),
        Cmd("home", r"^/1 1 home$")
    }

    in_terminator = '\r\n'
    out_terminator = '\r\n'

    def get_status(self):
        return f"@ 01 0 OK {self.device.state} -- 0"

    def get_position(self):
        return f"@ 01 0 OK {self.device.state} -- {self.device.position}"

    def move_relative(self, new_target):
        self.device.target = self.device.target + new_target

    def move_absolute(self, new_target):
        self.device.target = new_target

    def home(self):
        self.device.target = 0
        self.device.homed = True
