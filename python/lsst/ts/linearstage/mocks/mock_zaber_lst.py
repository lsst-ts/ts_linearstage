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

__all__ = ["LinearStageServer", "MockLSTV2"]

import asyncio
import inspect
import logging
import types
import typing

from zaber_motion.ascii import WarningFlags

from lsst.ts import simactuators, tcpip

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

    def __init__(self, port: int | None, log: logging.Logger, config: types.SimpleNamespace) -> None:
        super().__init__(
            port=port,
            host=tcpip.LOCAL_HOST,
            log=log,
            name="Zaber Mock Server",
            terminator=b"\n",
        )
        self.device: MockLSTV2 = MockLSTV2(address=config.daisy_chain_address)

    async def read_and_dispatch(self) -> None:
        """Read from the client and send a reply."""
        try:
            command: str = await self.read_str()
        except asyncio.IncompleteReadError as e:
            # Used for debugging received message
            self.log.info(f"{e.partial!r}")
            raise
        self.log.info(f"{command=} received.")
        reply: str = self.device.parse_message(command)
        self.log.debug(f"Writing {reply=}.")
        await self.write_str(reply + "\r")


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

    def __init__(self, address: int = 1) -> None:
        self.identified: bool = False
        self.address: int = address
        self.id: int = wizardry.ID
        self.system_serial: int = wizardry.SYSTEM_SERIAL
        self.version: str = wizardry.VERSION
        self.version_build: int = wizardry.VERSION_BUILD
        self.modified: bool = False
        self.axis_count: int = 1
        self.message_id: int | None = None
        self.max_packet: int = wizardry.MAX_PACKET
        self.max_word: int = wizardry.MAX_WORD
        self.position: simactuators.PointToPointActuator = simactuators.PointToPointActuator(
            min_position=0, max_position=100000000, speed=60000
        )
        self.axes: types.SimpleNamespace = types.SimpleNamespace(
            axis1=types.SimpleNamespace(
                address=1,
                id=wizardry.AXIS_ID,
                resolution=wizardry.AXIS_RESOLUTION,
                modified=False,
                position=simactuators.PointToPointActuator(
                    min_position=0, max_position=100000000, speed=60000
                ),
            ),
            axis2=types.SimpleNamespace(address=2, id=0, resolution="NA", modified=False),
            axis3=types.SimpleNamespace(address=3, id=0, resolution="NA", modified=False),
            axis4=types.SimpleNamespace(address=4, id=0, resolution="NA", modified=False),
        )
        self.homed = False
        self.log = logging.getLogger(__name__)

    def parse_message(self, msg: str) -> str:
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
            return f"@{self.address:02} 0 0 OK IDLE WR 0"
        msg = msg.lstrip("/")
        msg_array: list = msg.split(" ")
        msg_array[-1] = msg_array[-1].split(":")[0]
        count = len(msg_array)
        request = types.SimpleNamespace()
        request.device_id = msg_array[0]
        request.axis_id = msg_array[1]
        request.message_id = msg_array[2]
        match count:
            case 3:
                self.message_id = int(request.message_id)
                return self.do_status(**vars(request))
            case 4:
                request.command = msg_array[3]
            case 5:
                request.command = msg_array[3]
                request.parameters = msg_array[4]
            case 6:
                request.command = msg_array[3]
                request.sub_command = msg_array[4]
                request.parameters = msg_array[5]
            case 7:
                request.command = msg_array[3]
                request.sub_command = msg_array[4]
                request.sub_sub_command = msg_array[5]
                request.parameters = msg_array[6]
            case _:
                raise RuntimeError(f"Length of message of {count} is not implemented.")
        self.log.debug(f"{request=}")
        self.message_id = int(request.message_id)
        commands = inspect.getmembers(self, inspect.ismethod)
        for name, method in commands:
            if name == f"do_{request.command}":
                return method(**vars(request))

        raise NotImplementedError(f"do_{request.command} not implemented.")

    def do_get(self, **kwargs: typing.Any) -> str:
        """Perform the get command."""
        field = kwargs["parameters"]
        device_address = int(kwargs["device_id"])
        axis_address = int(kwargs["axis_id"])
        if axis_address != 0:
            axis = getattr(self.axes, f"axis{axis_address}")
        response = f"@{device_address:02} {axis_address} {self.message_id:02} OK IDLE -- "
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

    def do_storage(self, **kwargs: typing.Any) -> str:
        """Perform the storage command."""
        sub_command = kwargs["sub_command"]
        sub_sub_command = kwargs.get("sub_sub_command")
        field = kwargs["parameters"]
        device_address = int(kwargs["device_id"])
        axis_address = int(kwargs["axis_id"])
        response = f"@{device_address:02} {axis_address} {self.message_id:02} RJ IDLE -- "

        def do_get() -> str:
            """Perform the storage get command."""
            match field:
                case "zaber.label":
                    return response + "BADDATA"
                case _:
                    raise NotImplementedError(f"{field} not implemented")

        def do_axis() -> str:
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

    def do_driver(self, **kwargs: typing.Any) -> str:
        """Perform the driver command."""
        field = kwargs["parameters"]
        device_address = int(kwargs["device_id"])
        axis_address = int(kwargs["axis_id"])
        response = f"@{device_address:02} {axis_address} {self.message_id:02} OK IDLE -- "
        match field:
            case "disable":
                return response + "0"
            case "enable":
                return response + "0"
            case _:
                raise NotImplementedError(f"{field} is not implemented.")

    def do_home(self, **kwargs: typing.Any) -> str:
        """Perform the home command."""
        device_address = int(kwargs["device_id"])
        axis_address = int(kwargs["axis_id"])
        response = f"@{device_address:02} {axis_address} {self.message_id:02} OK IDLE -- "
        self.homed = True
        return response + "0"

    def do_move(self, **kwargs: typing.Any) -> str:
        """Peform the move command."""
        sub_command = kwargs["sub_command"]
        device_address = int(kwargs["device_id"])
        axis_address = int(kwargs["axis_id"])
        axis = getattr(self.axes, f"axis{axis_address}")
        response = f"@{device_address:02} {axis_address} {self.message_id:02} OK IDLE -- "

        def do_rel() -> str:
            """Perform the move rel command."""
            target = axis.position.position() + float(kwargs["parameters"])
            axis.position.set_position(position=target)
            return response + "0"

        def do_abs() -> str:
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

    def do_status(self, **kwargs: typing.Any) -> str:
        """Perform the status command."""
        device_address = int(kwargs["device_id"])
        axis_address = int(kwargs["axis_id"])
        moving = self.position.moving()
        if moving:
            status = "BUSY"
        else:
            status = "IDLE"
        response = f"@{device_address:02} {axis_address} {self.message_id:02} OK {status} -- "
        return response + "0"

    def do_warnings(self, **kwargs: typing.Any) -> str:
        device_address = int(kwargs["device_id"])
        axis_address = int(kwargs["axis_id"])
        moving = self.position.moving()
        response = f"@{device_address:02} {axis_address} {self.message_id:02} OK "
        if self.homed:
            flag = "--"
        else:
            flag = WarningFlags.NO_REFERENCE_POSITION
        if moving:
            status = "BUSY"
        else:
            status = "IDLE"
        if self.homed:
            response += f"{status} {flag} 00"
        else:
            response += f"{status} {flag} 00 {flag}"
        return response
