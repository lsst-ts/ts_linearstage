__all__ = ["ErrorCode"]

import enum


class ErrorCode(enum.Enum):
    CONNECTION_FAILED = enum.auto()
    DISABLE_MOTOR = enum.auto()
    ENABLE_MOTOR = enum.auto()
    HOME = enum.auto()
    MOVE_ABSOLUTE = enum.auto()
    MOVE_RELATIVE = enum.auto()
    POSITION = enum.auto()
    TELEMETRY = enum.auto()
