import unittest
import asynctest
import pathlib
import logging

from lsst.ts import salobj
from lsst.ts import LinearStage
from lsst.ts.idl.enums.LinearStage import DetailedState

logging.basicConfig()
logger = logging.getLogger(__name__)

TEST_CONFIG_DIR = pathlib.Path(__file__).parents[1].joinpath("tests", "data", "config")

CONFIGS = ["igus.yaml", "zaber.yaml"]


class LinearStageCscTestCase(salobj.BaseCscTestCase, asynctest.TestCase):
    def basic_make_csc(
        self, index, initial_state, config_dir, simulation_mode, **kwargs
    ):
        return LinearStage.LinearStageCSC(
            index=index,
            initial_state=initial_state,
            config_dir=TEST_CONFIG_DIR,
            simulation_mode=simulation_mode,
        )

    async def test_bin_script(self):
        await self.check_bin_script(
            name="LinearStage", exe_name="run_linearstage_csc.py", index=1
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
                        settingsToApply=config,
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
                logger.debug(f"Using config of {config}")
                async with self.make_csc(
                    index=1,
                    initial_state=salobj.State.STANDBY,
                    simulation_mode=1,
                    config_dir=TEST_CONFIG_DIR,
                ):
                    await self.remote.cmd_start.set_start(settingsToApply=config)
                    await self.remote.cmd_enable.start()

                    position_topic = await self.remote.tel_position.next(flush=True)
                    self.assertAlmostEqual(
                        position_topic.position, self.csc.component.position
                    )

    async def test_getHome(self):
        for config in CONFIGS:
            with self.subTest(config=config):
                logger.debug(f"Using config of {config}")
                async with self.make_csc(
                    index=1,
                    initial_state=salobj.State.STANDBY,
                    simulation_mode=1,
                    config_dir=TEST_CONFIG_DIR,
                ):
                    # Bring to enabled with correct config
                    await self.remote.cmd_start.set_start(settingsToApply=config)
                    await self.remote.cmd_enable.start()
                    await self.remote.cmd_getHome.set_start(timeout=10)

                    # At this point, with the igus stage, when you go back to
                    # stanbdy it disables the motor (applies the brake),
                    # however, internal status can be held. Check that it
                    # can come back to enabled and move.

    async def test_moveAbsolute(self):
        for config in CONFIGS:
            with self.subTest(config=config):
                logger.debug(f"Using config of {config}")
                async with self.make_csc(
                    index=1,
                    initial_state=salobj.State.STANDBY,
                    simulation_mode=1,
                    config_dir=TEST_CONFIG_DIR,
                ):
                    # Bring to enabled with correct config
                    await self.remote.cmd_start.set_start(settingsToApply=config)
                    await self.remote.cmd_enable.start()

                    _dist = 10  # [mm] - distance to travel

                    logger.debug("Try to move without being homed, this should fail")
                    with self.assertRaises(salobj.AckError):
                        await self.remote.cmd_moveAbsolute.set_start(
                            distance=_dist, timeout=10
                        )

                    # shortcut homing
                    # Now set the referencing to True
                    self.csc.referenced = True
                    if self.csc.stage_type == "Igus":
                        logger.debug("Faking homing step of Igus stage")
                        # set current position in the mock
                        self.csc.component.mock_ctrl.current_pos = 0.0
                        # Also set the controller mode since it would normally
                        # get set when homing
                        await self.csc.component.set_mode("position")

                    await self.remote.cmd_moveAbsolute.set_start(
                        distance=_dist, timeout=15
                    )

                    await self.assert_next_sample(
                        topic=self.remote.evt_detailedState,
                        detailedState=DetailedState.NOTMOVINGSTATE,
                    )
                    await self.assert_next_sample(
                        topic=self.remote.tel_position, flush=True, position=_dist
                    )

    async def test_moveRelative(self):
        async with self.make_csc(
            index=1, initial_state=salobj.State.ENABLED, simulation_mode=1
        ):
            await self.remote.cmd_moveRelative.set_start(distance=10, timeout=15)
            await self.assert_next_sample(
                topic=self.remote.tel_position, flush=True, position=10
            )
            await self.remote.cmd_moveRelative.set_start(distance=10, timeout=15)
            await self.assert_next_sample(
                topic=self.remote.tel_position, flush=True, position=20
            )

    # async def test_checkMotorInternalStatusPreservation(self):
    #     with self.subTest(config="igus"):
    #         logger.debug(f"Using config of {config}")
    #         async with self.make_csc(
    #             index=1,
    #             initial_state=salobj.State.STANDBY,
    #             simulation_mode=1,
    #             config_dir=TEST_CONFIG_DIR,
    #         ):
    #             # Bring to enabled with correct config
    #             await self.remote.cmd_start.set_start(settingsToApply=config)
    #             await self.remote.cmd_enable.start()
    #             await self.remote.cmd_getHome.set_start(timeout=10)
    #
    #             # At this point, with the igus stage, when you go back to
    #             # standby it disables the motor (applies the brake),
    #             # however, internal status can be held. Check that it
    #             # can come back to enabled and move.
    #             await self.remote.cmd_disable.start()
    #             # after motor shutdown (disabled)
    #             # status gives [0,  0,  0,  0,  0, 15,  0, 43, 13,  0,  0,
    #                           0, 96, 65,  0,  0,  0,  0,  2, 33, 22,]
    #             await self.remote.cmd_standby.start()
    #
    #             await self.remote.cmd_start.set_start(settingsToApply=config)
    #             await self.remote.cmd_enable.start()


if __name__ == "__main__":
    unittest.main()
