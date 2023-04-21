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
import unittest

from lsst.ts.linearstage.controllers import (
    Igus,
    interpret_read_telegram,
    telegrams_read,
    telegrams_write,
)


class TestIgusLinearStageStepper(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        config = types.SimpleNamespace(
            **{
                "socket_port": 502,
                "socket_address": "192.168.0.148",
                "feed_rate": 150,
                "maximum_stroke": 1000,
                "homing_speed": 30,
                "homing_acceleration": 20,
                "homing_timeout": 60,
                "motion_speed": 50,
                "motion_acceleration": 20,
            }
        )
        self.lsc = Igus(
            config=config, simulation_mode=True, log=logging.getLogger(__name__)
        )

    async def test_connect_disconnect(self):
        await self.lsc.connect()
        # request status
        status = await self.lsc.retrieve_status()
        self.assertEqual(tuple(status), telegrams_read["switch_on_disabled"])
        await self.lsc.disconnect()

    async def test_enable_motor(self):
        await self.lsc.connect()
        # # Disable the motor
        await self.lsc.disable_motor()

        # request status
        status = await self.lsc.retrieve_status()
        self.lsc.feed_constant = 150
        self.lsc.homing_speed = 30
        self.lsc.homing_acceleration = 20
        self.lsc.motion_speed = 50
        self.lsc.motion_acceleration = 25
        self.assertEqual(tuple(status), telegrams_read["ready_to_switch_on"])

        # Now enable the motor
        await self.lsc.enable_motor()
        # request status
        status = await self.lsc.retrieve_status()
        self.assertEqual(tuple(status), telegrams_read["operation_enabled"])

        # self.assertTrue(False)
        await self.lsc.disconnect()

    async def test_utils_interpret_read_telegram(self):
        # test for one that exists
        telegram = (0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2, 33, 6)
        mode = 6
        msg = interpret_read_telegram(telegram, mode)
        self.assertGreater(len(msg), 200)
        # Make sure it fails correctly
        telegram = (0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2, 5, 5)
        msg = interpret_read_telegram(telegram, mode)
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
        with self.assertRaises(TimeoutError):
            await self.lsc.poll_until_result([telegrams_read["switched_on"]], timeout=2)
