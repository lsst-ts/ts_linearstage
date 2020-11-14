__all__ = ["MockSerial", "MockLST"]

import logging
import queue
import inspect

from zaber.serial import AsciiCommand

import serial


class MockSerial:
    """Implements mock serial.

    Parameters
    ----------
    port : `str`
    baudrate : `int`
    bytesize : `int`
    parity
    stopbits
    timeout : `None` or `float`
    xonxoff : `bool`
    rtscts : `bool`
    write_timeout : `None` or `float`
    dsrdtr : `bool`
    inter_byte_timeout : `None` or `float`
    exclusive : `None`

    Attributes
    ----------
    log : `logging.Logger`
    name : `str`
    baudrate : `int`
    bytesize : `int`
    parity
    stopbits
    timeout : `None` or `float`
    xonxoff : `bool`
    rtscts : `bool`
    write_timeout : `None` or `float`
    dsrdts : `bool`
    inter_byte_timeout : `None` or `float`
    exclusive : `bool`
    opened : `bool`
    device : `MockLST`
    message_queue : `queue.Queue`
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
        msg = self.device.parse_message(data)
        self.log.debug(msg)
        self.message_queue.put(msg)
        self.log.info("Putting into queue")

    def close(self):
        """Close the serial connection.
        """
        self.log.info("Closing serial connection")


class MockLST:
    """Implements mock LinearStage.

    Attributes
    ----------
    log : `logging.Logger`
    position : `int`
    status : `str`
    device_number : `int`

    """

    def __init__(self):
        self.log = logging.getLogger(__name__)
        self.position = 0
        self.status = "IDLE"
        self.device_number = 1
        self.log.info("MockLST created")

    def parse_message(self, msg):
        """Parse and return the result of the message.

        Parameters
        ----------
        msg : `bytes`
            The message to parse.

        Returns
        -------
        reply : `bytes`
            The reply of the command parsed.

        Raises
        ------
        NotImplementedError
            Raised when command is not implemented.
        """
        self.log.info(msg)
        msg = AsciiCommand(msg)
        self.log.info(msg)
        split_msg = msg.data.split(" ")
        self.log.debug(split_msg)
        if any(char.isdigit() for char in split_msg[-1]):
            parameter = split_msg[-1]
            command = split_msg[:-1]
        else:
            parameter = None
            command = split_msg
        self.log.debug(parameter)
        if command != []:
            command_name = "_".join(command)
        else:
            command_name = ""
        self.log.debug(command_name)
        methods = inspect.getmembers(self, inspect.ismethod)
        if command_name == "":
            return self.do_get_status()
        else:
            for name, func in methods:
                if name == f"do_{command_name}":
                    self.log.debug(name)
                    if parameter is None:
                        reply = func()
                    else:
                        reply = func(parameter)
                    self.log.debug(reply)
                    return reply
        raise NotImplementedError()

    def do_get_pos(self):
        """Return the position of the device.

        Returns
        -------
        str
            The formatted reply
        """
        return f"@{self.device_number} 0 OK {self.status} -- {self.position}"

    def do_get_status(self):
        """Return the status of the device.

        Returns
        -------
        str
            The formatted reply.
        """
        return f"@{self.device_number} 0 OK {self.status} -- 0"

    def do_home(self):
        """Home the device.

        Returns
        -------
        str
            The formatted reply.
        """
        return f"@{self.device_number} 0 OK {self.status} -- 0"

    def do_move_abs(self, position):
        """Move the device using absolute position.

        Parameters
        ----------
        position : `int`

        Returns
        -------
        str
            The formatted reply
        """
        self.position = int(position)
        return f"@{self.device_number} 0 OK {self.status} -- 0"

    def do_move_rel(self, position):
        """Move the device using relative position.

        Parameters
        ----------
        position : `int`

        Returns
        -------
        str
            The formatted reply.
        """
        self.position += int(position)
        return f"@{self.device_number} 0 OK {self.status} -- 0"
