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
