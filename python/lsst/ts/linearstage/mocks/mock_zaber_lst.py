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

__all__ = ["MockSerial", "MockLST", "LinearStageServer", "MockLSTV2"]

import asyncio
import inspect
import logging
import queue
import types

import serial
from lsst.ts import simactuators, tcpip
from zaber_motion.ascii import WarningFlags

from .. import wizardry


class LinearStageServer(tcpip.OneClientReadLoopServer):
    """Implment the mock linearstage server.

    Parameters
    ----------
    port : `int | None`
        The port of the mock server.
    log : `logging.Logger`
        The log of the mock server.

    Attributes
    ----------
    device : `MockLST`
        The mock device that handles replies.
    """

    def __init__(self, port: int | None, log: logging.Logger) -> None:
        super().__init__(
            port=port,
            host=tcpip.LOCAL_HOST,
            log=log,
            name="Zaber Mock Server",
            terminator=b"\n",
        )
        self.device: MockLSTV2 = MockLSTV2()

    async def read_and_dispatch(self) -> None:
        """Read from the client and send a reply."""
        try:
            command: str = await self.read_str()
        except asyncio.IncompleteReadError as e:
            # Used for debugging received message
            self.log.info(f"{e.partial}")
            raise
        self.log.info(f"{command=} received.")
        reply: str = self.device.parse_message(command)
        self.log.debug(f"Writing {reply=}.")
        await self.write_str(reply)


class MockLSTV2:
    """Mock the zaber stage.

    Attributes
    ----------
    address : `int`
        The device address.
    id : `int`
        The ID number of the device.
    system_serial : `int`
        The serial number of the system.
    version : `str`
        The version string of the firmware.
    version_build : `int`
        The version build number of the firmware.
    modified : `bool`
        Has the device been modified?
    axis_count : `int`
        The number of axes attached to the device.
    message_id : `int` | `None`
        The ID of the current message.
    max_packet : `int`
        The number of bytes allowed in a packet.
    max_word : `int`
        The max size of a word.
    position : `lsst.ts.simactuators.PointToPointActuator`
        The encoder position along the stage.
    axes : `types.SimpleNamespace`
        The information from each axis.
    """

    def __init__(self) -> None:
        self.identified: bool = False
        self.address: int = 0
        self.id: int = wizardry.ID
        self.system_serial: int = wizardry.SYSTEM_SERIAL
        self.version: str = wizardry.VERSION
        self.version_build: int = wizardry.VERSION_BUILD
        self.modified: bool = False
        self.axis_count: int = 1
        self.message_id: int | None = None
        self.max_packet: int = wizardry.MAX_PACKET
        self.max_word: int = wizardry.MAX_WORD
        self.position: simactuators.PointToPointActuator = (
            simactuators.PointToPointActuator(
                min_position=0, max_position=1000000, speed=60000
            )
        )
        self.axes: types.SimpleNamespace = types.SimpleNamespace(
            axis1=types.SimpleNamespace(
                address=1,
                id=wizardry.AXIS_ID,
                resolution=wizardry.AXIS_RESOLUTION,
                modified=False,
                position=simactuators.PointToPointActuator(
                    min_position=0, max_position=1000000, speed=60000
                ),
            ),
            axis2=types.SimpleNamespace(
                address=2, id=0, resolution="NA", modified=False
            ),
            axis3=types.SimpleNamespace(
                address=3, id=0, resolution="NA", modified=False
            ),
            axis4=types.SimpleNamespace(
                address=4, id=0, resolution="NA", modified=False
            ),
        )
        self.homed = False
        self.log = logging.getLogger(__name__)

    def parse_message(self, msg) -> str:
        """Parse the message.

        Parameters
        ----------
        msg : `str`
            The mesage received from the client.

        Returns
        -------
        `str`
            The reply that was generated.
        """
        if msg == "/0 0 00":
            return "@01 0 0 OK IDLE WR 0"
        msg = msg.lstrip("/")
        msg = msg.split(" ")
        msg[-1] = msg[-1].split(":")[0]
        count = len(msg)
        request = types.SimpleNamespace()
        request.device_id = msg[0]
        request.axis_id = msg[1]
        request.message_id = msg[2]
        match count:
            case 3:
                self.message_id = request.message_id
                return self.do_status(**vars(request))
            case 4:
                request.command = msg[3]
            case 5:
                request.command = msg[3]
                request.parameters = msg[4]
            case 6:
                request.command = msg[3]
                request.sub_command = msg[4]
                request.parameters = msg[5]
            case 7:
                request.command = msg[3]
                request.sub_command = msg[4]
                request.sub_sub_command = msg[5]
                request.parameters = msg[6]
            case _:
                raise RuntimeError(f"Length of message of {count} is not implemented.")
        self.log.debug(f"{request=}")
        self.message_id = request.message_id
        commands = inspect.getmembers(self, inspect.ismethod)
        for name, method in commands:
            if name == f"do_{request.command}":
                return method(**vars(request))

        raise NotImplementedError(f"do_{request.command} not implemented.")

    def do_get(self, **kwargs) -> str:
        """Perform the get command."""
        field = kwargs["parameters"]
        device_address = int(kwargs["device_id"])
        axis_address = int(kwargs["axis_id"])
        if axis_address != 0:
            axis = getattr(self.axes, f"axis{axis_address}")
        response = (
            f"@{device_address:02} {axis_address} {self.message_id:02} OK IDLE -- "
        )
        match field:
            case "deviceid":
                return response + f"{self.id}"
            case "system.serial":
                return response + f"{self.system_serial}"
            case "version":
                return response + f"{self.version}"
            case "version.build":
                return response + f"{self.version_build}"
            case "device.hw.modified":
                return response + f"{int(self.modified)}"
            case "system.axiscount":
                return response + f"{self.axis_count}"
            case "resolution":
                return response + f"{getattr(axis, 'resolution')}"
            case "peripheralid":
                return response + f"{getattr(axis, 'id')}"
            case "peripheral.serial":
                return response + "0"
            case "peripheral.hw.modified":
                return response + f"{int(getattr(axis, 'modified'))}"
            case "status":
                return response + "0"
            case "comm.command.packets.max":
                return response + f"{self.max_packet}"
            case "comm.packet.size.max":
                return response + f"{self.max_packet}"
            case "comm.word.size.max":
                return response + f"{self.max_word}"
            case "get.settings.max":
                return response + "0"
            case "pos":
                return response + f"{axis.position.position()}"
            case _:
                raise NotImplementedError(f"{field} not implemented")

    def do_storage(self, **kwargs) -> str:
        """Perform the storage command."""
        sub_command = kwargs["sub_command"]
        sub_sub_command = kwargs.get("sub_sub_command")
        field = kwargs["parameters"]
        device_address = int(kwargs["device_id"])
        axis_address = int(kwargs["axis_id"])
        response = (
            f"@{device_address:02} {axis_address} {self.message_id:02} RJ IDLE -- "
        )

        def do_get():
            """Perform the storage get command."""
            match field:
                case "zaber.label":
                    return response + "BADDATA"
                case _:
                    raise NotImplementedError(f"{field} not implemented")

        def do_axis():
            """Perform the storage axis command."""
            match sub_sub_command:
                case "get":
                    match field:
                        case "zaber.label":
                            return response + "BADDATA"
                        case _:
                            raise NotImplementedError(f"{field} is not implemented")
                case _:
                    raise NotImplementedError(f"{sub_sub_command} is not implemented.")

        match sub_command:
            case "get":
                return do_get()
            case "axis":
                return do_axis()
            case _:
                raise NotImplementedError(f"{sub_command} not implemented.")

    def do_driver(self, **kwargs) -> str:
        """Perform the driver command."""
        field = kwargs["parameters"]
        device_address = int(kwargs["device_id"])
        axis_address = int(kwargs["axis_id"])
        response = (
            f"@{device_address:02} {axis_address} {self.message_id:02} OK IDLE -- "
        )
        match field:
            case "disable":
                return response + "0"
            case "enable":
                return response + "0"
            case _:
                raise NotImplementedError(f"{field} is not implemented.")

    def do_home(self, **kwargs) -> str:
        """Perform the home command."""
        device_address = int(kwargs["device_id"])
        axis_address = int(kwargs["axis_id"])
        response = (
            f"@{device_address:02} {axis_address} {self.message_id:02} OK IDLE -- "
        )
        return response + "0"

    def do_move(self, **kwargs) -> str:
        """Peform the move command."""
        sub_command = kwargs["sub_command"]
        device_address = int(kwargs["device_id"])
        axis_address = int(kwargs["axis_id"])
        axis = getattr(self.axes, f"axis{axis_address}")
        response = (
            f"@{device_address:02} {axis_address} {self.message_id:02} OK IDLE -- "
        )

        def do_rel():
            """Perform the move rel command."""
            target = axis.position.position() + float(kwargs["parameters"])
            axis.position.set_position(position=target)
            return response + "0"

        def do_abs():
            """Perform the move abs command."""
            target = float(kwargs["parameters"])
            axis.position.set_position(position=target)
            return response + "0"

        match sub_command:
            case "rel":
                return do_rel()
            case "abs":
                return do_abs()
            case _:
                raise NotImplementedError(f"{sub_command} is not implemented.")

    def do_status(self, **kwargs) -> str:
        """Perform the status command."""
        device_address = int(kwargs["device_id"])
        axis_address = int(kwargs["axis_id"])
        moving = self.position.moving()
        if moving:
            status = "BUSY"
        else:
            status = "IDLE"
        response = (
            f"@{device_address:02} {axis_address} {self.message_id:02} OK {status} -- "
        )
        return response + "0"

    def do_warnings(self, **kwargs):
        device_address = int(kwargs["device_id"])
        axis_address = int(kwargs["axis_id"])
        if self.homed:
            flag = "--"
        else:
            flag = WarningFlags.NO_REFERENCE_POSITION
        response = f"@{device_address:02} {axis_address} {self.message_id:02} OK IDLE {flag} 01 {flag}"
        return response


class MockSerial:
    """Implements mock serial.

    Parameters
    ----------
    port : `str`
        The serial port.
    baudrate : `int`
        The baudrate of the port.
    bytesize : `int`
        The number of bytes.
    parity
        The parity check.
    stopbits
        The number of stopbits.
    timeout : `None` or `float`
        The timeout.
    xonxoff : `bool`
        The transfer feed.
    rtscts : `bool`
        The flow control.
    write_timeout : `None` or `float`
        The write timeout.
    dsrdtr : `bool`
        dsrdtr.
    inter_byte_timeout : `None` or `float`
        The inter byte timeout.
    exclusive : `None`
        Exclusive lock of the port.

    Attributes
    ----------
    log : `logging.Logger`
        The log of the mock serial.
    name : `str`
        The name of the port.
    baudrate : `int`
        The baudrate.
    bytesize : `int`
        The size of the byte.
    parity
        The parity check type.
    stopbits
        The number of stopbits.
    timeout : `None` or `float`
        The timeout.
    xonxoff : `bool`
        xonoff.
    rtscts : `bool`
        rtscts.
    write_timeout : `None` or `float`
        The write timeout.
    dsrdts : `bool`
        dsrdts
    inter_byte_timeout : `None` or `float`
        The inter byte timeout.
    exclusive : `bool`
        Exclusivity.
    opened : `bool`
        Whether the port is opened?
    device : `MockLST`
        The mock device.
    message_queue : `queue.Queue`
        Contains the messages that are to be sent to the client.
    """

    def __init__(
        self,
        port,
        baudrate=9600,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=None,
        xonxoff=False,
        rtscts=False,
        write_timeout=None,
        dsrdtr=False,
        inter_byte_timeout=None,
        exclusive=None,
    ):
        self.log = logging.getLogger(__name__)
        self.name = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self.xonxoff = xonxoff
        self.rtscts = rtscts
        self.write_timeout = write_timeout
        self.dsrdtr = dsrdtr
        self.inter_byte_timeout = inter_byte_timeout
        self.exclusive = exclusive
        self.opened = False

        self.device = MockLST()
        self.message_queue = queue.Queue()

        self.log.info("MockSerial created")

    def readline(self, size=-1):
        """Read the line.

        Parameters
        ----------
        size : `int`, optional
            The size of the line.

        Returns
        -------
        msg : `bytes`
            The message from the queue.
        """
        self.log.info("Reading from queue")
        msg = self.message_queue.get()
        self.log.info(msg.encode())
        return msg.encode()

    def write(self, data):
        """Write the data.

        Parameters
        ----------
        data : `bytes`
            The command message.
        """
        self.log.info(data)
        msg = self.device.parse_message(data.decode())
        self.log.debug(msg)
        self.message_queue.put(msg)
        self.log.info("Putting into queue")

    def close(self):
        """Close the serial connection."""
        self.log.info("Closing serial connection")


class MockLST:
    """Implements mock LinearStage.

    Attributes
    ----------
    log : `logging.Logger`
        The log.
    position : `int`
        The position.
    status : `str`
        The status.
    device_number : `int`
        The device address.

    """

    def __init__(self):
        self.log = logging.getLogger(__name__)
        self.position = 0.0
        self.status = "IDLE"
        self.device_number = 1
        self.log.info("MockLST created")

    def parse_message(self, msg):
        """Parse the message and return a reply.

        Parameters
        ----------
        msg : `str`
            The message to be parsed.

        Returns
        -------
        reply : `str`
            The response to the message received.
        """
        try:
            self.log.info(f"{msg=} received.")
            msg = msg.rstrip("\r\n").split(" ")
            msg[0].lstrip("/")
            msg[1]
            command = msg[2]
            parameters = msg[3:]
        except IndexError:
            reply = self.do_status()
            return reply
        methods = inspect.getmembers(self, inspect.ismethod)
        for name, func in methods:
            if name == f"do_{command}":
                if parameters:
                    reply = func(*parameters)
                    return reply
                else:
                    reply = func()
                    return reply

        self.log.info(f"{command} not supported.")

    def do_identify(self):
        """Perform the identify command."""
        return self.identity

    def do_status(self):
        """Perform the status command."""
        return f"@{self.device_number} 0 OK {self.status} -- 0"

    def do_get(self, field):
        """Return the position of the device.

        field : `str`
            The field data to return.

        Returns
        -------
        str
            The formatted reply
        """
        match field:
            case "pos":
                return f"@{self.device_number} 0 OK {self.status} -- {self.position}"
            case "status":
                return f"@{self.device_number} 0 OK {self.status} -- 0"
            case "deviceid:42":
                return "@01 0 OK IDLE FO 30342"
            case _:
                self.log.info(f"{field=} is not recognized.")

    def do_home(self):
        """Home the device.

        Returns
        -------
        str
            The formatted reply.
        """
        return f"@{self.device_number} 0 OK {self.status} -- 0"

    def do_move(self, mode, position):
        """Move the device using absolute position.

        Parameters
        ----------
        mode : `str`
            The movement mode.
        position : `int`
            The target to move to/by.
        Returns
        -------
        str
            The formatted reply
        """
        match mode:
            case "abs":
                self.position = float(position)
            case "rel":
                self.position += float(position)
            case _:
                self.log.info(f"{mode=} is not recognized.")
        return f"@{self.device_number} 0 OK {self.status} -- 0"
