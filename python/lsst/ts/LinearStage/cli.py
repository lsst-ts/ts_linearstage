__all__ = ["execute_csc"]

import asyncio

from . import LinearStageCSC


def execute_csc():
    asyncio.run(LinearStageCSC.amain(index=True))
