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

import logging
import types
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

    def __init__(
        self, config: types.SimpleNamespace, log: logging.Logger, simulation_mode: int
    ):
        self.config: types.SimpleNamespace = config
        self.log: logging.Logger = log
        self.simulation_mode: int = simulation_mode

    # TODO DM-45058 Add a referenced property
    @property
    @abstractmethod
    def referenced(self):
        raise NotImplementedError()

    @abstractmethod
    async def move_relative(self, value) -> None:
        """Move the stage from position to target.

        Parameters
        ----------
        value : `float`
            The target to move by.
        """
        pass

    @abstractmethod
    async def move_absolute(self, value) -> None:
        """Move the stage to target.

        Parameters
        ----------
        value : `float`
            The target to move to.
        """
        pass

    @abstractmethod
    async def home(self) -> None:
        """Home the stage which gives it a reference position."""
        pass

    @abstractmethod
    async def enable_motor(self) -> None:
        """Enable movement of the motor."""
        pass

    @abstractmethod
    async def disable_motor(self) -> None:
        """Disable movement of the motor."""
        pass

    @abstractmethod
    async def update(self) -> None:
        """Get the position and status of the stage."""
        pass

    @property
    @abstractmethod
    def connected(self) -> bool:
        """Is the client connected?"""
        pass

    @abstractmethod
    async def connect(self) -> None:
        """Connect to the device."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the device."""
        pass

    @classmethod
    @abstractmethod
    def get_config_schema(cls) -> dict:
        """Get the device specific configuration schema."""
        pass
