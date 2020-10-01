import unittest

import asynctest

from lsst.ts import salobj
from lsst.ts import LinearStage


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
        async with self.make_csc(index=1, initial_state=salobj.State.STANDBY):
            await self.check_standard_state_transitions(
                enabled_commands=[
                    "getHome",
                    "moveAbsolute",
                    "moveRelative",
                    "stop"])


if __name__ == "__main__":
    unittest.main()
