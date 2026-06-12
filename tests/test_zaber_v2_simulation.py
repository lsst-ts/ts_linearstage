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

from lsst.ts import salobj
from lsst.ts.linearstage.config_schema import CONFIG_SCHEMA
from lsst.ts.linearstage.controllers import ZaberV2
from lsst.ts.linearstage.mocks.mock_zaber_lst import MockLSTV2


def test_config_schema_accepts_simulation_enabled_axes() -> None:
    validator = salobj.DefaultingValidator(CONFIG_SCHEMA)

    config = validator.validate(
        {
            "instances": [
                {
                    "sal_index": 101,
                    "target_position_minimum": 0,
                    "target_position_maximum": 25,
                    "simulation_enabled_axes": [1, 3],
                    "stage_type": "ZaberV2",
                    "stage_config": {
                        "hostname": "localhost",
                        "port": 4001,
                        "daisy_chain_address": 1,
                        "stage_name": "X-MCC4",
                        "serial_number": 115313,
                    },
                }
            ]
        }
    )

    assert config["instances"][0]["simulation_enabled_axes"] == [1, 3]


def test_zaber_v2_config_schema_accepts_simulation_enabled_axes() -> None:
    validator = salobj.DefaultingValidator(ZaberV2.get_config_schema())

    config = validator.validate(
        {
            "hostname": "localhost",
            "port": 4001,
            "daisy_chain_address": 1,
            "stage_name": "X-MCC4",
            "serial_number": 115313,
            "simulation_enabled_axes": [1, 3],
        }
    )

    assert config["simulation_enabled_axes"] == [1, 3]


def test_mock_zaber_v2_uses_simulation_enabled_axes() -> None:
    mock_device = MockLSTV2(address=1, enabled_axes=[1, 3])

    assert mock_device.axes.axis1.id != 0
    assert mock_device.axes.axis2.id == 0
    assert mock_device.axes.axis3.id != 0
    assert mock_device.axes.axis4.id == 0
