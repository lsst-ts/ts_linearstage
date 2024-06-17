__all__ = ["ErrorCode"]

import enum


# TODO Move into ts-xml enums.
class ErrorCode(enum.IntEnum):
    """Error codes that indicate why the CSC went to fault state."""

    CONNECTION_FAILED = enum.auto()
    DISABLE_MOTOR = enum.auto()
    ENABLE_MOTOR = enum.auto()
    HOME = enum.auto()
    MOVE_ABSOLUTE = enum.auto()
    MOVE_RELATIVE = enum.auto()
    POSITION = enum.auto()
    TELEMETRY = enum.auto()
