from lsst.ts.LinearStage.controllers.igus_dryve import IgusLinearStageStepper
from lsst.ts.LinearStage.controllers.igus_dryve.igusDryveTelegrams import (
    telegrams_write,
    telegrams_read,
    #    telegrams_read_errs,
)
from lsst.ts.LinearStage.controllers.igus_dryve.igus_utils import (
    interpret_read_telegram,
)
import unittest
import logging

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.propagate = True


class TestIgusLinearStageStepper(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.lsc = IgusLinearStageStepper(simulation_mode=True, log=logger)

    async def test_connect_disconnect(self):
        await self.lsc.connect()
        # request status
        status = await self.lsc.retrieve_status()
        logger.debug(f"Status received is {status}")
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
        self.lsc.homing_speed = 30
        self.lsc.homing_acceleration = 20
        self.lsc.motion_speed = 50
        self.lsc.motion_acceleration = 25
        self.assertEqual(tuple(status), telegrams_read["ready_to_switch_on"])

        # Now enable the motor
        logger.debug("\n Now enable the motor")
        await self.lsc.enable_motor(True)
        # request status
        status = await self.lsc.retrieve_status()
        self.assertEqual(tuple(status), telegrams_read["operation_enabled"])

        # self.assertTrue(False)
        await self.lsc.disconnect()

    async def test_utils_interpret_read_telegram(self):
        # test for one that exists
        telegram = tuple(
            [0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2, 33, 6]
        )
        mode = 6
        msg = interpret_read_telegram(telegram, mode)
        logger.debug(f"Received interpretation of: {msg}")
        self.assertGreater(len(msg), 200)
        # Make sure it fails correctly
        telegram = tuple(
            [0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2, 5, 5]
        )
        msg = interpret_read_telegram(telegram, mode)
        logger.debug(f"Received interpretation of: {msg}")
        self.assertTrue(
            f"The following telegram could not be interpreted: \n {telegram}" in msg
        )

    async def test_weird_state_handling(self):
        await self.lsc.connect()
        await self.lsc.send_telegram(
            telegrams_write["unexpected_response_check"],
            check_handshake=True,
            return_response=False,
        )
        logger.debug("Try to move without being homed, this should fail")
        with self.assertRaises(TimeoutError):
            await self.lsc.poll_until_result([telegrams_read["switched_on"]], timeout=2)
