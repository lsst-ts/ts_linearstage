import asyncio
import logging
from lsst.ts.LinearStage.controllers.igus_dryve.igusDryveTelegrams import (
    telegrams_write,
    #    telegrams_read,
    #    telegrams_read_errs,
)

logging.basicConfig()
logger = logging.getLogger(__name__)

_STD_TIMEOUT = 5  # seconds


async def read_telegram(reader, timeout=_STD_TIMEOUT):
    """Reads a telegram from the igus controller.
    This is required because it sends packets of different lengths
    Byte 6 tells how many additional bytes are sent.
    One can't read more bytes or it might start parsing the next message.
    This method reads 6 bytes, then determines how much to read, then
    reads the rest. It then reassembles the two reads into a single
    message and returns it.

    Returns
    -------
    full_telegram: `list`
        Full telegram of proper length

    """

    # Read first 6 bytes, then it'll say how many more to read
    prefix0 = await asyncio.wait_for(reader.read(6), timeout=timeout)
    # prefix0 = await reader.read(6)
    prefix = list(prefix0)
    # self.log.debug(f'byte 5 of read is {prefix[5]}')
    if prefix[5] == 0:
        raise KeyError(
            f"Command prefix has a length of 0 in byte 6, meaning command is not formatted correctly"
        )
    suffix0 = await reader.read(prefix[5])
    suffix = list(suffix0)
    # self.log.debug(f'The remaining bytes are: {suffix}')
    full_telegram = prefix + suffix
    return full_telegram


def derive_handshake(telegram):
    """Derive what the expected handshake is for a given command.
    The handshake will consist of parts of the command, but not all.

    Parameters
    ----------

    telegram : `list`
        Command sent to controller

    Returns
    -------
    handshake : `list`
        Expected handshake from controller. Returns None if no handshake
        is to be expected
    """

    # Check that the telegram is a write telegram
    if telegram[9] == 1:
        # Expected handshake is the sent command, but 19 bytes long with
        # the last 4 bytes at zero
        handshake = list(telegram[0:19])
        handshake[5] = 13
        for i in range(15, 19):
            handshake[i] = 0
        handshake = tuple(handshake)
        # logging.debug(f"Derived handshake of {handshake}")
    elif telegram is telegrams_write["status_request"]:
        return None
    else:
        raise KeyError(
            "Telegram type not recognized, cannot derive expected handshake."
        )

    return handshake


async def interpret_read_telegram(self, telegram, mode):
    """Breaks down what a telegram means when received from the controller.

    The telegram is up to 24 bytes (but numbering is zero based, 0-23).
    Byte 12 and 13 contain the command type. For example,

    Tye Statusword 6041h telegram means that byte 12 is 96 in decimal
    and 60 in hexadecimal. Byte 13 is 65 in decimal (41 in hexadecimal).

    Bits 0-7 of the statusword are in byte 19, bits 8-15 are in 20

    """
    # A Statusword 6041h telegram
    # means that byte 12 = 60h (hex) = 96 in decimal
    # and byte 13 = 41h (hex) = 65 in decimal
    if telegram[12] == 96 and telegram[13] == 65:
        if telegram[19] == 33:
            # 33 is 10110, so switched on, operation enabled, voltage enable?
            # What is voltage enable? FIXME - not in manual
            # Appears to happen when a limit is hit while in homing mode.
            logging.log(
                "Interpreted as 6041h, byte 19 gives switched on, operation enabled, voltage enable."
                "May occur when a limit is hit and has been cleared, but the state is in homing mode."
                "Switch to position mode to clear the issue."
            )
        if telegram[19] == 39:
            # 39 is 100111, so ready to switch on, switched on,
            # operation enabled, quick stop
            # this happens after homing is completed
            # if byte 20 == 22, then it's referenced
            # if byte 20 = 2, then homing being executed
            logging.log(
                "Interpreted as 6041h, byte 19 gives switch on, switched on, operation enabled, quick stop"
            )
        # Byte 20 is mode dependent, 6 is homing, 1 is position
        if mode == 6:
            if telegram[20] == 2:  # 01
                logging.log("Interpreted as 6041h, byte 20 gives: DI7 enabled")
            if telegram[20] == 22:  # 10110 (bits 12, 11, 10, 9, 8 on the right)
                # homing executed successfully sets bits 10 and 12 high
                logging.log(
                    "Interpreted as 6041h, byte 20 gives: DI7 enabled, homing executed successfully"
                )
            if telegram[20] == 34:  # 100010 (bits 13, 12, 11, 10, 9, 8 on the right)
                # homing executed successfully sets bits 10 and 12 high
                logging.log(
                    "Interpreted as 6041h, byte 20 gives: DI7 enabled, ... unsure"
                )
        if mode == 0 or mode == 1:
            if telegram[20] == 2:  # 01
                logging.log("Interpreted as 6041h, byte 20 gives: DI7 enabled")
            if telegram[20] == 4:  # 100
                logging.log(
                    "Interpreted as 6041h, byte 20 gives: Target Reached - but this doesn't make sense. "
                    "This happens when DI7 is not enabled or the drive profile in the controller is not set"
                )
            if telegram[20] == 6:  # 110
                logging.log(
                    "Interpreted as 6041h, byte 20 gives: DI7 enabled, Target Reached"
                )
