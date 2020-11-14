from lsst.ts.LinearStage.controllers.igus_dryve import IgusLinearStageStepper
from lsst.ts.LinearStage.controllers.igus_dryve.igusDryveTelegrams import (
    # telegrams_write,
    telegrams_read,
    #    telegrams_read_errs,
)
import asynctest
import logging

logging.basicConfig()
logger = logging.getLogger(__name__)


class TestIgusLinearStageStepper(asynctest.TestCase):
    async def setUp(self):
        self.lsc = IgusLinearStageStepper(simulation_mode=True, log=logger)

    async def test_connect_disconnect(self):
        await self.lsc.connect()
        # request status
        status = await self.lsc.retrieve_status()
        print(f"Status received is {status}")
        self.assertEqual(tuple(status), telegrams_read["switch_on_disabled"])
        await self.lsc.disconnect()

    async def test_enable_motor(self):
        await self.lsc.connect()
        # # Disable the motor
        await self.lsc.enable_motor(False)

        # request status
        logger.debug("\n Now requesting status")
        status = await self.lsc.retrieve_status()
        self.lsc.feed_constant = 150
        self.lsc.homing_speed = 150
        self.lsc.homing_acceleration = 50
        self.lsc.motion_speed = 150
        self.lsc.motion_acceleration = 50
        self.assertEqual(tuple(status), telegrams_read["ready_to_switch_on"])

        # Now enable the motor
        logger.debug("\n Now enable the motor")
        await self.lsc.enable_motor(True)
        # request status
        status = await self.lsc.retrieve_status()
        self.assertEqual(tuple(status), telegrams_read["operation_enabled"])

        await self.lsc.disconnect()
