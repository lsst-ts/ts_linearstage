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

import asyncio
import pathlib
import unittest

import pytest
from lsst.ts import linearstage, salobj
from lsst.ts.idl.enums.LinearStage import DetailedState

TEST_CONFIG_DIR = pathlib.Path(__file__).parents[1].joinpath("tests", "data", "config")

CONFIGS = ["igus.yaml", "zaber.yaml"]


class LinearStageCscTestCase(salobj.BaseCscTestCase, unittest.IsolatedAsyncioTestCase):
    def basic_make_csc(
        self, index, initial_state, config_dir, simulation_mode, **kwargs
    ):
        return linearstage.LinearStageCSC(
            index=index,
            initial_state=initial_state,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=simulation_mode,
            override=kwargs.get("override"),
        )

    async def test_bin_script(self):
        await self.check_bin_script(
            name="LinearStage", exe_name="run_linearstage", index=1
        )

    async def test_standard_state_transitions(self):
        for config in CONFIGS:
            with self.subTest(config=config):
                async with self.make_csc(
                    index=1,
                    initial_state=salobj.State.STANDBY,
                    simulation_mode=1,
                    config_dir=TEST_CONFIG_DIR,
                ):
                    await self.check_standard_state_transitions(
                        enabled_commands=[
                            "getHome",
                            "moveAbsolute",
                            "moveRelative",
                            "stop",
                        ],
                        override=config,
                    )

    # This will work with salobj 6.1 when it's released
    # async def test_telemetry(self):
    #     # This doesn't grab the config
    #     configs = ["igus.yaml", "zaber.yaml"]
    #     configs = ["igus.yaml"]
    #     for config in configs:
    #         with self.subTest(config=config):
    #             logger.debug(f"Using config of {config}")
    #             async with self.make_csc(
    #                 index=1,
    #                 initial_state=salobj.State.ENABLED,
    #                 simulation_mode=1,
    #                 config_dir=TEST_CONFIG_DIR,
    #                 settingsToApply=config,
    #             ):
    #                 await self.assert_next_sample(
    #                     topic=self.remote.tel_position, position=0
    #                 )

    async def test_telemetry(self):
        for config in CONFIGS:
            with self.subTest(config=config):
                async with self.make_csc(
                    index=1,
                    initial_state=salobj.State.STANDBY,
                    simulation_mode=1,
                    config_dir=TEST_CONFIG_DIR,
                ):
                    await self.remote.cmd_start.set_start(configurationOverride=config)
                    await self.remote.cmd_enable.start()

                    position_topic = await self.remote.tel_position.next(flush=True)
                    self.assertAlmostEqual(
                        position_topic.position, self.csc.component.position
                    )

    async def test_getHome(self):
        for config in CONFIGS:
            with self.subTest(config=config):
                async with self.make_csc(
                    index=1,
                    initial_state=salobj.State.STANDBY,
                    simulation_mode=1,
                    config_dir=TEST_CONFIG_DIR,
                ):
                    # Bring to enabled with correct config
                    await self.remote.cmd_start.set_start(configurationOverride=config)
                    await self.remote.cmd_enable.start()
                    await self.remote.cmd_getHome.set_start(timeout=10)

                    # At this point, with the igus stage, when you go back to
                    # standby it disables the motor (applies the brake),
                    # however, internal status can be held. Check that it
                    # can come back to enabled and move.

    async def test_moveAbsolute(self):
        for config in CONFIGS:
            with self.subTest(config=config):
                async with self.make_csc(
                    index=1,
                    initial_state=salobj.State.STANDBY,
                    simulation_mode=1,
                    config_dir=TEST_CONFIG_DIR,
                ):
                    # Bring to enabled with correct config
                    await self.remote.cmd_start.set_start(configurationOverride=config)
                    await self.remote.cmd_enable.start()

                    _dist = 10  # [mm] - distance to travel

                    with self.assertRaises(salobj.AckError):
                        await self.remote.cmd_moveAbsolute.set_start(distance=_dist)

                    # shortcut homing
                    # Now set the referencing to True
                    self.csc.referenced = True
                    if hasattr(self.csc.component, "mock_ctrl"):
                        # set current position in the mock
                        self.csc.component.mock_ctrl.current_pos = 0.0
                        # Also set the controller mode since it would normally
                        # get set when homing
                        await self.csc.component.set_mode("position")

                    await self.remote.cmd_moveAbsolute.set_start(distance=_dist)
                    await asyncio.sleep(1.5)
                    await self.assert_next_sample(
                        topic=self.remote.evt_detailedState,
                        detailedState=DetailedState.NOTMOVINGSTATE,
                    )
                    await self.assert_next_sample(
                        topic=self.remote.tel_position, flush=True, position=_dist
                    )

    async def test_moveRelative(self):
        for config in CONFIGS:
            with self.subTest(config=config):
                async with self.make_csc(
                    index=1,
                    initial_state=salobj.State.ENABLED,
                    simulation_mode=1,
                    config_dir=TEST_CONFIG_DIR,
                    override=config,
                ):
                    await self.remote.cmd_moveRelative.set_start(
                        distance=10, timeout=15
                    )
                    if config == "zaber.yaml":
                        await self.assert_next_sample(
                            topic=self.remote.tel_position, flush=True, position=10
                        )
                    else:
                        # Igus behaves weirdly with this method but no idea
                        # what
                        # behavior should be. So just going to handle this
                        # specially.
                        posit = await self.remote.tel_position.next(flush=True)
                        assert posit.position == pytest.approx(11.2, abs=0.05)
                    await self.remote.cmd_moveRelative.set_start(
                        distance=10, timeout=15
                    )
                    if config == "zaber.yaml":
                        await self.assert_next_sample(
                            topic=self.remote.tel_position, flush=True, position=20
                        )
                    else:
                        posit = await self.remote.tel_position.next(flush=True)
                        assert posit.position == pytest.approx(21.2, abs=0.05)


if __name__ == "__main__":
    unittest.main()
