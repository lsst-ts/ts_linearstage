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
from lsst.ts.xml.enums.LinearStage import DetailedState
from parameterized import parameterized

TEST_CONFIG_DIR = pathlib.Path(__file__).parents[1].joinpath("tests", "data", "config")

CONFIGS = ["igus.yaml", "zaber.yaml"]

STD_TIMEOUT = 20

INDEXES = [2, 3]


class LinearStageCscTestCase(salobj.BaseCscTestCase, unittest.IsolatedAsyncioTestCase):
    def basic_make_csc(
        self,
        index,
        initial_state,
        config_dir=TEST_CONFIG_DIR,
        simulation_mode=1,
        override="",
    ):
        return linearstage.LinearStageCSC(
            index=index,
            initial_state=initial_state,
            config_dir=config_dir,
            simulation_mode=simulation_mode,
            override=override,
        )

    async def test_bin_script(self):
        await self.check_bin_script(
            name="LinearStage", exe_name="run_linearstage", index=1
        )

    @parameterized.expand(INDEXES)
    async def test_standard_state_transitions(self, index):
        async with self.make_csc(
            index=index,
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
                ]
            )

    async def test_invalid_index(self):
        with self.assertRaises(salobj.AckError):
            async with self.make_csc(
                index=4,
                initial_state=salobj.State.STANDBY,
                simulation_mode=1,
                config_dir=TEST_CONFIG_DIR,
            ):
                await self.remote.cmd_start.set_start(timeout=10)

    @parameterized.expand(INDEXES)
    async def test_telemetry(self, index):
        async with self.make_csc(
            index=index,
            initial_state=salobj.State.ENABLED,
            simulation_mode=1,
            config_dir=TEST_CONFIG_DIR,
        ):
            position_topic = await self.assert_next_sample(
                topic=self.remote.tel_position, flush=True
            )
            if self.csc.salinfo.index == 2:
                if (
                    self.csc.salinfo.component_info.topics["tel_position"]
                    .fields["position"]
                    .count
                    == 1
                ):
                    assert position_topic.position == pytest.approx(1.2)
                else:
                    assert position_topic.position == pytest.approx([1.2])
            else:
                if (
                    self.csc.salinfo.component_info.topics["tel_position"]
                    .fields["position"]
                    .count
                    == 1
                ):
                    assert position_topic.position == pytest.approx(0)
                else:
                    assert position_topic.position == pytest.approx([0])

    @parameterized.expand(INDEXES)
    async def test_getHome(self, index):
        async with self.make_csc(
            index=index,
            initial_state=salobj.State.ENABLED,
            simulation_mode=1,
            config_dir=TEST_CONFIG_DIR,
        ):
            # Bring to enabled with correct config
            await self.remote.cmd_getHome.set_start(timeout=STD_TIMEOUT)

            # At this point, with the igus stage, when you go back to
            # standby it disables the motor (applies the brake),
            # however, internal status can be held. Check that it
            # can come back to enabled and move.

    @parameterized.expand(INDEXES)
    async def test_moveAbsolute(self, index):
        async with self.make_csc(
            index=index,
            initial_state=salobj.State.ENABLED,
            simulation_mode=1,
            config_dir=TEST_CONFIG_DIR,
        ):
            _dist = 10  # [mm] - distance to travel

            with salobj.assertRaisesAckError():
                await self.remote.cmd_moveAbsolute.set_start(distance=_dist)
            await self.remote.cmd_getHome.set_start(timeout=STD_TIMEOUT)
            if hasattr(self.csc.component, "mock_ctrl"):
                # set current position in the mock
                self.csc.component.mock_ctrl.current_pos = 0.0
                # Also set the controller mode since it would normally
                # get set when homing
                await self.csc.component.set_mode("position")

            await self.remote.cmd_moveAbsolute.set_start(distance=_dist)
            await self.assert_next_sample(
                topic=self.remote.evt_detailedState,
                detailedState=DetailedState.NOTMOVINGSTATE,
            )
            await asyncio.sleep(10)
            position = await self.assert_next_sample(
                topic=self.remote.tel_position, flush=True
            )
            if (
                self.csc.salinfo.component_info.topics["tel_position"]
                .fields["position"]
                .count
                == 1
            ):
                assert position.position == pytest.approx(10, rel=1.5e-6)
            else:
                assert position.position == pytest.approx([10], rel=1.5e-6)

    @parameterized.expand(INDEXES)
    async def test_moveRelative(self, index):
        async with self.make_csc(
            index=index,
            initial_state=salobj.State.STANDBY,
            simulation_mode=1,
            config_dir=TEST_CONFIG_DIR,
        ):
            await self.remote.cmd_start.set_start()
            await self.remote.cmd_enable.set_start()
            await self.remote.cmd_moveRelative.set_start(
                distance=10, timeout=STD_TIMEOUT
            )
            if self.csc.salinfo.index == 1 or self.csc.salinfo.index == 3:
                await asyncio.sleep(10)
                position = await self.assert_next_sample(
                    topic=self.remote.tel_position, flush=True
                )
                if (
                    self.csc.salinfo.component_info.topics["tel_position"]
                    .fields["position"]
                    .count
                    == 1
                ):
                    assert position.position == pytest.approx(10, rel=1.2e-6)
                else:
                    assert position.position == pytest.approx([10], rel=1.2e-6)
            else:
                # Igus behaves weirdly with this method but no idea
                # what
                # behavior should be. So just going to handle this
                # specially.
                posit = await self.assert_next_sample(
                    topic=self.remote.tel_position, flush=True
                )
                if (
                    self.csc.salinfo.component_info.topics["tel_position"]
                    .fields["position"]
                    .count
                    == 1
                ):
                    assert posit.position == pytest.approx(11.2, abs=0.05)
                else:
                    assert posit.position == pytest.approx([11.2], abs=0.05)
            await self.remote.cmd_moveRelative.set_start(
                distance=10, timeout=STD_TIMEOUT
            )
            if self.csc.salinfo.index == 1 or self.csc.salinfo.index == 3:
                await asyncio.sleep(10)
                position = await self.assert_next_sample(
                    topic=self.remote.tel_position, flush=True
                )
                if (
                    self.csc.salinfo.component_info.topics["tel_position"]
                    .fields["position"]
                    .count
                    == 1
                ):
                    assert position.position == pytest.approx(20, rel=1.2e-6)
                else:
                    assert position.position == pytest.approx([20], rel=1.2e-6)
            else:
                posit = await self.assert_next_sample(
                    topic=self.remote.tel_position, flush=True
                )
                if (
                    self.csc.salinfo.component_info.topics["tel_position"]
                    .fields["position"]
                    .count
                    == 1
                ):
                    assert posit.position == pytest.approx(21.2, abs=0.05)
                else:
                    assert posit.position == pytest.approx([21.2], abs=0.05)
