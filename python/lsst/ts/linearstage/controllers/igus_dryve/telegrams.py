# This file contains the dictionaries of telegrams that are send/received
# to the igusDryveController

telegrams_write = {
    "status_request": tuple(
        [0, 0, 0, 0, 0, 13, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2]
    ),
    "shutdown": tuple(
        [0, 0, 0, 0, 0, 15, 0, 43, 13, 1, 0, 0, 96, 64, 0, 0, 0, 0, 2, 6, 0]
        # [0, 0, 0, 0, 14, 0, 43, 13, 1, 0, 0, 96, 64, 0, 0, 0, 0, 1, 6]
    ),
    "switch_on": tuple(
        [0, 0, 0, 0, 0, 15, 0, 43, 13, 1, 0, 0, 96, 64, 0, 0, 0, 0, 2, 7, 0]
    ),
    "enable_operation": tuple(
        [0, 0, 0, 0, 0, 15, 0, 43, 13, 1, 0, 0, 96, 64, 0, 0, 0, 0, 2, 15, 0]
    ),
    "start_motion": tuple(
        [0, 0, 0, 0, 0, 15, 0, 43, 13, 1, 0, 0, 96, 64, 0, 0, 0, 0, 2, 31, 0]
    ),
    "get_mode": tuple([0, 0, 0, 0, 0, 13, 0, 43, 13, 0, 0, 0, 96, 97, 0, 0, 0, 0, 1]),
    "get_position": tuple(
        [0, 0, 0, 0, 0, 13, 0, 43, 13, 0, 0, 0, 96, 100, 0, 0, 0, 0, 4]
    ),
    # This is a fake behaviour to intentionally put the controller
    # in an unexpected state for testing error handling.
    "unexpected_response_check": tuple(
        [0, 0, 0, 0, 0, 15, 0, 43, 13, 1, 0, 0, 96, 64, 0, 0, 0, 0, 2, 30, 2]
    ),
}
telegrams_read = {
    # Status of initial state after powering on
    # and enabled bit is set (manually)
    # It does not appear possible to go back to this state once leaving it
    "switch_on_disabled": tuple(
        [0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2, 64, 6]
    ),
    # Status after successful shutdown command
    "ready_to_switch_on": tuple(
        [0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2, 33, 6]
    ),
    # Status after successful switch_on command
    "switched_on": tuple(
        [0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2, 35, 6]
    ),
    # Below occurs after enable_operation command
    "operation_enabled": tuple(
        [0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2, 39, 6]
    ),
    # Occurs when homing is completed successfully
    "target_reached": tuple(
        [0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2, 39, 22]
    ),
    "homing_being_executed": tuple(
        [0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2, 39, 2]
    ),
    "move_being_executed": tuple(
        [0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2, 39, 2]
    ),
    # the following is only for testing error handling and the parsing
    # of a telegram for interpretation given in error messages
    "weird_state1": tuple(
        [0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2, 39, 22]
    ),
}
# These are the responses that you do not want to see from the
# controller as it means something is not correct
telegrams_read_errs = {
    # Status when turned on but remote mode not set correctly
    # (see Section 6.4.1 in the Manual)
    # Note that the drive needs to be enabled via DI7 (manually
    # or by applying a voltage
    "switch_on_disabled_no_remote": tuple(
        [0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2, 64, 4]
    ),
}
# What is this?
# Received response telegram of
# [0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2, 33, 22]
#
# DEBUG:LinearStage.IgusLinearStageStepper:Looking for
#  (0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2, 8, 2)
#  and got
#  (0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2, 39, 22)

# After power cycling CSC and trying to re-enable
# DEBUG:LinearStage.IgusLinearStageStepper:Looking for
#  (0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2, 33, 2)
#  and got
#  (0, 0, 0, 0, 0, 15, 0, 43, 13, 0, 0, 0, 96, 65, 0, 0, 0, 0, 2, 33, 6)
