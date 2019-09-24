#!/usr/bin/env python

import logging
import asyncio
import argh

from lsst.ts.linearStage.csc import LinearStageCSC


@argh.arg('-v', '--verbose', choices=['info', ' debug'])
@argh.arg('address', type=int)
def main(port, address, index, verbose="info", frequency=0.5):
    log = logging.getLogger()
    ch = logging.StreamHandler()
    if verbose == "info":
        log.setLevel(logging.INFO)
        ch.setLevel(logging.INFO)
    elif verbose == "debug":
        log.setLevel(logging.DEBUG)
        ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    ch.setFormatter(formatter)
    log.addHandler(ch)
    argh.ArghParser()
    LinearStageCSC(port, address, int(index), frequency=float(frequency))
    log.info("LinearStage {0} initialized".format(address))
    loop = asyncio.get_event_loop()
    try:
        log.info('Running CSC (Hit ctrl+c to stop it')
        loop.run_forever()
    except KeyboardInterrupt:
        log.info("Stopping CBP CSC")
    except Exception as e:
        log.error(e)
    finally:
        loop.close()


if __name__ == '__main__':
    argh.dispatch_command(main)
