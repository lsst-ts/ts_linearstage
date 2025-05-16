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

import logging
import types

import pytest
from lsst.ts.linearstage.controllers import Zaber


@pytest.mark.skip("Deprecated.")
class TestZaberLSTStage:
    @pytest.fixture(scope="class")
    def lsc(self) -> Zaber:
        config: types.SimpleNamespace = types.SimpleNamespace(
            **{
                "port": "/dev/ttyLinearStage1",
                "steps_per_mm": 8000,
                "daisy_chain_address": 1,
            }
        )
        lsc: Zaber = Zaber(
            config=config, simulation_mode=True, log=logging.getLogger(__name__)
        )
        return lsc
