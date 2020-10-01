#!/usr/bin/env python
import asyncio

from lsst.ts.LinearStage.csc import LinearStageCSC

asyncio.run(LinearStageCSC.amain(index=True))
