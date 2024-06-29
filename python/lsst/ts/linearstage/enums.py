__all__ = ["ErrorCode"]

import enum


# TODO DM-45062 Move into ts-xml enums.
class ErrorCode(enum.IntEnum):
    """Error codes that indicate why the CSC went to fault state."""

    CONNECTION_FAILED = enum.auto()
    """Connection to the device failed."""
    DISABLE_MOTOR = enum.auto()
    """Disabling the motor failed."""
    ENABLE_MOTOR = enum.auto()
    """Enabling the motor failed."""
    HOME = enum.auto()
    """Homing the stage failed."""
    MOVE_ABSOLUTE = enum.auto()
    """The absolute move failed."""
    MOVE_RELATIVE = enum.auto()
    """The relative move failed."""
    POSITION = enum.auto()
    """Failed to get the position."""
    TELEMETRY = enum.auto()
    """The telemetry loop failed."""
    STOP = enum.auto()
