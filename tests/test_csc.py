import unittest

import asynctest

from lsst.ts import salobj
from lsst.ts import LinearStage
from lsst.ts.idl.enums.LinearStage import DetailedState


class LinearStageCscTestCase(salobj.BaseCscTestCase, asynctest.TestCase):
    def basic_make_csc(
            self,
            index,
            initial_state,
            config_dir,
            simulation_mode,
            **kwargs):
        return LinearStage.LinearStageCSC(
            index=index,
            initial_state=initial_state,
            config_dir=config_dir,
            simulation_mode=simulation_mode)

    async def test_bin_script(self):
        await self.check_bin_script(name="LinearStage", exe_name="run_linearstage_csc.py", index=1)

    async def test_standard_state_transitions(self):
        async with self.make_csc(index=1, initial_state=salobj.State.STANDBY, simulation_mode=1):
            await self.check_standard_state_transitions(
                enabled_commands=[
                    "getHome",
                    "moveAbsolute",
                    "moveRelative",
                    "stop"])

    async def test_telemetry(self):
        async with self.make_csc(index=1, initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.assert_next_sample(topic=self.remote.tel_position, position=0)

    async def test_getHome(self):
        async with self.make_csc(index=1, initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.remote.cmd_getHome.set_start(timeout=15)

    async def test_moveAbsolute(self):
        async with self.make_csc(index=1, initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.remote.cmd_moveAbsolute.set_start(distance=10, timeout=15)
            await self.assert_next_sample(
                topic=self.remote.evt_detailedState,
                detailedState=DetailedState.NOTMOVINGSTATE)
            await self.assert_next_sample(topic=self.remote.tel_position, flush=True, position=10)

    async def test_moveRelative(self):
        async with self.make_csc(index=1, initial_state=salobj.State.ENABLED, simulation_mode=1):
            await self.remote.cmd_moveRelative.set_start(distance=10, timeout=15)
            await self.assert_next_sample(topic=self.remote.tel_position, flush=True, position=10)
            await self.remote.cmd_moveRelative.set_start(distance=10, timeout=15)
            await self.assert_next_sample(topic=self.remote.tel_position, flush=True, position=20)


if __name__ == "__main__":
    unittest.main()
