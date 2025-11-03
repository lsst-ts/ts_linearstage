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

import asyncio
import logging

from .telegrams import telegrams_write

logging.basicConfig()
logger = logging.getLogger(__name__)

_STD_TIMEOUT = 5  # seconds


async def read_telegram(reader: asyncio.StreamReader, timeout: float = _STD_TIMEOUT) -> list:
    """Reads a telegram from the igus controller.

    This is required because it sends packets of different lengths
    Byte 6 tells how many additional bytes are sent.
    One can't read more bytes or it might start parsing the next message.
    This method reads 6 bytes, then determines how much to read, then
    reads the rest. It then reassembles the two reads into a single
    message and returns it.

    Parameters
    ----------
    reader : `asyncio.StreamReader`
    timeout : `float`

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
            "Command prefix has a length of 0 in byte 6, meaning command is not formatted correctly"
        )
    suffix0 = await reader.read(prefix[5])
    suffix = list(suffix0)
    # self.log.debug(f'The remaining bytes are: {suffix}')
    full_telegram = prefix + suffix
    return full_telegram


def derive_handshake(telegram: tuple | None) -> tuple | None:
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
    if telegram is None:
        raise RuntimeError("Telegram is None.")

    # Check that the telegram is a write telegram
    if telegram[9] == 1:
        # Expected handshake is the sent command, but 19 bytes long with
        # the last 4 bytes at zero
        handshake = list(telegram[0:19])
        handshake[5] = 13
        for i in range(15, 19):
            handshake[i] = 0
        configured_handshake = tuple(handshake)
        # logging.debug(f"Derived handshake of {handshake}")
    elif telegram is telegrams_write["status_request"]:
        return None
    else:
        raise KeyError("Telegram type not recognized, cannot derive expected handshake.")

    return configured_handshake


def interpret_read_telegram(telegram: tuple, mode: int) -> str:
    """Breaks down what a telegram means when received from the controller.

    The telegram is up to 24 bytes (but numbering is zero based, 0-23).
    Byte 12 and 13 contain the command type. For example,

    Tye Statusword 6041h telegram means that byte 12 is 96 in decimal
    and 60 in hexadecimal. Byte 13 is 65 in decimal (41 in hexadecimal).

    Bits 0-7 of the statusword are in byte 19, bits 8-15 are in 20

    Parameters
    ----------
    telegram : `bytearray`
    mode : `int`

    """
    # A Statusword 6041h telegram
    # means that byte 12 = 60h (hex) = 96 in decimal
    # and byte 13 = 41h (hex) = 65 in decimal
    msg = ""
    if telegram[12] == 96 and telegram[13] == 65:
        if telegram[19] == 33:
            # 33 is 100001, so switched on, and quick stopped
            # Appears to happen when a limit is hit (also while in homing mode?
            msg_piece = (
                f"Interpreted as 6041h, byte 19 [{telegram[19]}] gives "
                "switched on, quick stop active. "
                "\n May occur when a limit is "
                "hit and has been cleared, but the state is in "
                "homing mode. \n Switch to position mode to clear "
                "the issue? The enable signal (DI7) may also "
                "need a reset. Lastly a power cycle."
            )
            logger.debug(msg_piece)
            msg = msg + (msg_piece)

        elif telegram[19] == 39:
            # 39 is 100111, so ready to switch on, switched on,
            # operation enabled, quick stop
            # this happens after homing is completed
            # if byte 20 == 22, then it's referenced
            # if byte 20 = 2, then homing being executed
            msg_piece = (
                f"\n Interpreted as 6041h, byte 19 [{telegram[19]}] gives switch on, "
                "switched on, operation enabled, quick stop"
            )
            logger.debug(msg_piece)
            msg = msg + (msg_piece)
        elif telegram[19] == 8:
            # 8 is 1000, this is a fault
            msg_piece = (
                f"\n Interpreted as 6041h, byte 19 [{telegram[19]}] says fault, "
                "reset the fault bit in the controller as the reset function"
                "is not yet implemented in the CSC"
            )
            logger.debug(msg_piece)
            msg = msg + (msg_piece)
        elif telegram[19] == 64:
            # 8 is 1000000
            msg_piece = f"\n Interpreted as 6041h, byte 19 [{telegram[19]}] says switch on disabled, "
            logger.debug(msg_piece)
            msg = msg + (msg_piece)

        # Byte 20 is mode dependent, 6 is homing mode, 1 is position
        if mode == 6:
            msg = msg + (f"\n Currently in homing mode [{mode}]")
            if telegram[20] == 2:  # 01
                msg = msg + (f"\n Interpreted as 6041h, byte 20 [{telegram[20]}] gives: DI7 enabled")
            elif telegram[20] == 22:  # 10110 (bits 12, 11, 10, 9, 8 on the right)
                # homing executed successfully sets bits 10 and 12 high
                msg = msg + (
                    f"\n Interpreted as 6041h, byte 20 [{telegram[20]}] gives: DI7 "
                    f"enabled, homing executed successfully"
                )
            elif telegram[20] == 34:  # 100010 (bits 13, 12, 11, 10, 9, 8 on the right)
                # homing executed successfully sets bits 10 and 12 high
                msg = msg + (f"Interpreted as 6041h, byte 20 [{telegram[20]}] gives: DI7 enabled, ... unsure")
            else:
                msg = msg + f"Could not interpret byte 20 [{telegram[20]}], for homing mode {mode}"
        if mode == 0 or mode == 1:
            msg = msg + (f"Currently in mode ({mode}). 1 = Profile Position Mode, 0 = no mode assigned")
            if telegram[20] == 2:  # 01
                msg = msg + (f"Interpreted as 6041h, byte 20 [{telegram[20]}] gives: DI7 enabled")
            elif telegram[20] == 4:  # 100
                msg = msg + (
                    f"Interpreted as 6041h, byte 20 [{telegram[20]}] gives: Target Reached"
                    f" - but this doesn't make sense. "
                    "This happens when DI7 is not enabled or the drive profile in the "
                    "controller is not set"
                )
            elif telegram[20] == 6:  # 110
                msg = msg + (
                    f"Interpreted as 6041h, byte 20 [{telegram[20]}] gives: DI7 enabled, Target Reached"
                )
            elif telegram[20] == 18:  # 10010
                msg = msg + (
                    f"Interpreted as 6041h, byte 20 [{telegram[20]}] gives: DI7 enabled, "
                    f"Target NOT Reached, setpoint applied."
                )
            else:
                msg = msg + f"Could not interpret byte 20 [{telegram[20]}] in mode {mode}."
    # Check to make sure that there is something new to add
    if "Interpreted" not in msg:
        msg = f"\n The following telegram could not be interpreted: \n {telegram}"

    return msg
