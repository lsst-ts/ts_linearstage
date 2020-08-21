# import asyncio
import unittest
from lsst.ts import salobj
from lsst.ts import LinearStage
import asynctest


class Harness:
    def __init__(self, initial_state):
        salobj.test_utils.set_random_lsst_dds_domain()
        self.csc = LinearStage.csc.LinearStageCSC(port="/dev/null", address=1, index=1)
        self.csc.model._ls = LinearStage.hardware.MockLinearStageComponent()
        self.remote = salobj.Remote(domain=self.csc.domain, name="LinearStage", index=1)

    async def __aenter__(self):
        await self.csc.start_task
        await self.remote.start_task
        return self

    async def __aexit__(self, *args):
        await self.csc.close()


class CscTestCase(asynctest.TestCase):
    @unittest.skip("")
    async def test_home(self):
        async with Harness(initial_state=salobj.State.ENABLED) as harness:
            state = await harness.remote.evt_summaryState.next(flush=False, timeout=30)
            self.assertEqual(state.summaryState, salobj.State.ENABLED)
            await harness.remote.cmd_getHome.start(timeout=30)
            position = harness.remote.tel_position.get()
            self.assertEqual(position.position, 0)

    @unittest.skip("")
    async def test_move_relative(self):
        async with Harness(initial_state=salobj.State.ENABLED) as harness:
            state = await harness.remote.evt_summaryState.next(flush=False, timeout=30)
            self.assertEqual(state.summaryState, salobj.State.ENABLED)
            harness.remote.cmd_moveRelative.distance = 5
            await harness.remote.cmd_moveRelative.start(timeout=30)
            position = harness.remote.tel_position.get()
            self.assertEqual(position.position, 40)
