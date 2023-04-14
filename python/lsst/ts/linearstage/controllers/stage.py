__all__ = ["Stage"]

from abc import ABC, abstractmethod


class Stage(ABC):
    """Create interface for devices that move along a track.

    Parameters
    ----------
    config : `types.Simplenamespace`
        The manufacturer specific settings.
    log : `logging.Logger`
        The log object
    simulation_mode : `bool`
        Is the stage controller in simulation mode?

    Attributes
    ----------
    config : `types.Simplenamespace`
        The settings for a specific stage.
    log : `logging.Logger`
        The SAL emitter log for DDS publication.
    simulation_mode:
        Is the stage in simulation mode?
    """

    def __init__(self, config, log, simulation_mode):
        self.config = config
        self.log = log
        self.simulation_mode = simulation_mode

    @abstractmethod
    def move_relative(self):
        pass

    @abstractmethod
    def move_absolute(self):
        pass

    @abstractmethod
    def home(self):
        pass

    @abstractmethod
    def enable_motor(self):
        pass

    @abstractmethod
    def disable_motor(self):
        pass

    @abstractmethod
    def update(self):
        pass

    @property
    @abstractmethod
    def connected(self):
        pass

    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def disconnect(self):
        pass

    @classmethod
    @abstractmethod
    def get_config_schema(cls):
        pass
