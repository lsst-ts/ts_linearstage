__all__ = ["ZaberLSTStage"]

import asyncio
import logging
import os
import pty

from lsst.ts.linearstage.mocks.mock_zaber_lst import MockSerial
from serial import SerialException
from zaber import serial as zaber

logging.basicConfig()
logger = logging.getLogger(__name__)

_LOCAL_HOST = "127.0.0.1"
_STD_TIMEOUT = 20  # standard timeout
_ZABER_MOVEMENT_TIME = 3  # time to wait for zaber to complete movement/homing


class ZaberLSTStage:
    """A class representing the ZaberLST linear stage device.
    This device connected via a serial connection.

    Parameters
    ----------

    simulation_mode : `bool`
        Is the stage in simulation mode.

    log : `logging.Logger`
        A log for the class.

    Attributes
    ----------

    connected : `bool`
        Is the stage connected.

    commander : `zaber.serial.AsciiDevice`
        Commands the serial device.

    serial_port : `str`
        The name of the port for the device.

    address : `int`
        The address of the device along the chain.

    position : `str`
        This holds the position of the linear stage. It starts at none as
        device requires homing to be done before it can be moved.

    reply_flags : `dict`
        This is a dictionary which contains all of the reply flags
        corresponding to what they mean.

    warning_flags : `dict`
        This is a dictionary which contains all of the warning flags which
        correspond to what those flags mean.

    simulation_mode : `bool`
        Is the hardware in simulation mode.

    """

    def __init__(self, simulation_mode, log) -> None:
        self.log = log.getChild("ZaberLSTStage")
        self.connected = False
        self.commander = None
        self.device_address = None
        self.address = 1
        self.position = None
        self.status = None
        self.reply_flags = {
            "BADDATA": "improperly formatted or invalid data",
            "AGAIN": "The command cannot be processed right now. "
            "The user or application should send the command again.",
            "BADAXIS": "The command was sent with an axis number greater than the number of axes available.",
            "BADCOMMAND": "The command or setting is incorrect or invalid.",
            "BADMESSAGEID": "A message ID was provided, but was not either -- or a number from 0 to 99.",
            "DEVICEONLY": "An axis number was specified when trying to execute a device only command.",
            "FULL": "The device has run out of permanent storage and cannot accept the command.",
            "LOCKSTEP": "An axis cannot be moved using normal motion commands because it is part of a "
            "lockstep group.",
            "NOACCESS": "The command or setting is not available at the current access level.",
            "PARKED": "The device cannot move because it is currently parked.",
            "STATUSBUSY": "The device cannot be parked, nor can certain settings be changed, "
            "because it is currently busy.",
        }
        self.warning_flags = {
            "WR": "No reference position",
            "--": "No Warning",
            "FD": "The driver has disabled itself due to overheating.",
            "FQ": "The encoder-measured position may be unreliable. "
            "The encoder has encountered a read error due to poor sensor alignment, "
            "vibration, dirt or other environmental conditions.",
            "FS": "Stalling was detected and the axis has stopped itself.",
            "FT": "The lockstep group has exceeded allowable twist and has stopped.",
            "FB": "A previous streamed motion could not be executed because it failed a precondition "
            "(e.g. motion exceeds device bounds, calls nested too deeply).",
            "FP": "Streamed or sinusoidal motion was terminated because an axis slipped "
            "and thus the device deviated from the requested path.",
            "FE": "The target limit sensor cannot be reached or is faulty.",
            "WH": "The device has a position reference, but has not been homed. "
            "As a result, calibration has been disabled.",
            "WL": "A movement operation did not complete due to a triggered limit sensor. "
            "This flag is set if a movement operation is interrupted by a limit sensor "
            "and the No Reference Position (WR) warning flag is not present.",
            "WP": "The saved calibration data type for the specified peripheral.serial value "
            "is unsupported by the current peripheral id.",
            "WV": "The supply voltage is outside the recommended operating range of the device. "
            "Damage could result to the device if not remedied.",
            "WT": "The internal temperature of the controller has exceeded the recommended limit for the "
            "device.",
            "WM": "While not in motion, the axis has been forced out of its position.",
            "NC": "Axis is busy due to manual control via the knob.",
            "NI": "A movement operation (command or manual control) was requested "
            "while the axis was executing another movement command. "
            "This indicates that a movement command did not complete.",
            "ND": "The device has slowed down while following a streamed motion path "
            "because it has run out of queued motions.",
            "NU": "A setting is pending to be updated or a reset is pending.",
            "NJ": "Joystick calibration is in progress. Moving the joystick will have no effect.",
        }

        self.simulation_mode = bool(simulation_mode)
        self.log.debug(
            f"Initialized ZaberLSTStage, simulation mode is {self.simulation_mode}"
        )

    def configure(self, config):
        """Configure the settings.

        Parameters
        ----------
        config : `types.SimpleNamespace`
        """
        self.steps_conversion = config.steps_per_mm
        if not self.simulation_mode:
            self.port = config.serial_port
            self.address = config.daisy_chain_address

    async def connect(self):
        """Connect to the Stage."""
        if not self.simulation_mode:
            self.commander = zaber.AsciiDevice(
                zaber.AsciiSerial(self.port), self.address
            )
            self.connected = True
        else:
            main, reader = pty.openpty()
            serial = zaber.AsciiSerial(os.ttyname(main))
            serial._ser = MockSerial("")
            self.commander = zaber.AsciiDevice(serial, self.address)
            self.connected = True
        self.log.info("Connected")

    async def disconnect(self):
        """Disconnect from the stage."""
        self.commander.port.close()
        self.commander = None
        self.connected = False  # Why can't this get set? This affects the zaber tests
        self.log.info("Disconnected from stage")

    async def enable_motor(self, value):
        """This method enables the motor and gets it ready to move.
        This includes transitioning the controller into the enabled/ready
        state and removing the brake (if appropriate).

        In the case of the zaberLST stage, there is no brake and it is
        always enabled

        Parameters
        ----------
        value : `bool`
            True to enable the motor, False to disable the motor.
        """
        self.log.debug(
            f"Inside enable_motor with value set to {value}."
            "Nothing to do for zaberLST stage"
        )

    async def move_absolute(self, value):
        """Move the stage using absolute position. Stage must have been
         homed prior to calling this method.

        The method uses a try-catch block to handle the Timeout error
        exception.
        It sends the command which returns a reply that is logged and then
        check for accepted or rejected status according to SAL specifications.
        If the command is accepted then the command begins executing.
        The device is polled for its status until the device is idle.
        If the command finishes successfully then it is logged and the
        position is set by the get_position function.

        Parameters
        ----------
        value : `int`
            The number of millimeters(converted) to move the stage.

        Raises
        ------
        Exception
            Raised when the command is rejected
        e : `TimeoutError`
            Raised when the serial port times out.

        """

        try:
            reply = self.commander.send(
                "move abs {}".format(int(value * self.steps_conversion))
            )
            self.log.info(reply)
            status_dictionary = self.check_reply(reply)
            if status_dictionary is False:
                raise Exception("Command rejected")
        except TimeoutError as e:
            self.log.error(e)
            raise

        # Wait 3s for stage to complete motion
        await asyncio.sleep(_ZABER_MOVEMENT_TIME)

    async def move_relative(self, value):
        """Move the stage using relative position.

        This method begins by establishing a try-catch block which handles the
        timeout exception by logging the error and proper SAL code.
        The command is then sent to the device where a reply is ostensibly
        returned.
        The reply is checked for acknowledgement or rejection and handled
        accordingly.
        If the command is accepted the device will perform the move and poll
        the device until it is idle returning SAL codes.
        The position attribute is updated using the get_position function.

        Parameters
        ----------
        value : `int`
            The number of millimeters(converted) to move the stage.

        Raises
        ------
        Exception
            Raised when command is rejected.
        e : `TimeoutError`
            Raised when serial port times out.
        """
        try:
            self.log.debug("move rel {}".format(int(value * self.steps_conversion)))
            reply = self.commander.send(
                "move rel {}".format(int(value * self.steps_conversion))
            )
            self.log.info(reply)
            status_dictionary = self.check_reply(reply)
            if status_dictionary is False:
                raise Exception("Command rejected")

        except TimeoutError as e:
            self.log.error(e)
            self.log.info("Command timeout")
            raise

        # Wait 3s for stage to complete motion
        await asyncio.sleep(_ZABER_MOVEMENT_TIME)

    async def get_home(self):
        """Home the Zaber stage by returning to the beginning of the track.

        The method begins by forming an AsciiCommand for the home command.
        The try-catch block is then established for the rest of the method in
        order to catch the timeout error and handle it appropriately.
        The command is sent to the device and a reply is likely returned.
        The reply is then checked for accepted or rejected status.
        If the command is accepted then the command begins to perform.
        The device is polled until idle while returning the appropriate SAL
        codes.
        If the command finishes successfully then the SAL code is logged.

        Raises
        ------
        e : `serial.SerialException`
            Raised when the serial port has a problem.

        """
        cmd = zaber.AsciiCommand("{} home".format(self.address))
        try:
            reply = self.commander.send(cmd)
            self.log.info(reply)
            self.check_reply(reply)
        except SerialException as e:
            self.log.error(e)
            self.log.info("Command for device timed out")
            raise

        # Wait 3s for stage to complete motion
        await asyncio.sleep(_ZABER_MOVEMENT_TIME)

    def check_reply(self, reply):
        """Check the reply for any issues/

        This method has 4 if-else clauses that it checks for any normal or
        abnormal operation of the linear stage.

        Parameters
        ----------
        reply : `str`
            This is the reply that is to be checked.

        Returns
        -------
        bool
            Is the command accepted.
        """
        self.log.info(reply)
        if reply.reply_flag == "RJ" and reply.warning_flag != "--":
            self.log.warning(
                "Command rejected by device {} for {}".format(
                    self.address, self.warning_flags[reply.warning_flag]
                )
            )
            return False
        elif reply.reply_flag == "RJ" and reply.warning_flag == "--":
            self.log.error(
                "Command rejected due to {}".format(
                    self.reply_flags.get(reply.data, reply.data)
                )
            )
            return False
        elif reply.reply_flag == "OK" and reply.warning_flag != "--":
            self.log.warning(
                "Command accepted but probably would return improper result due to {}".format(
                    self.warning_flags[reply.warning_flag]
                )
            )

            return True
        else:
            self.log.info("Command accepted by device #{}".format(self.address))
            return True

    def get_position(self):
        """Return the position of the stage.

        It works by sending a command to the device and ostensibly is given a
        reply.
        The reply is then checked for acceptance or rejection by the device
        and the position is then set by the return of the reply's data if
        successful.

        Returns
        -------
        float
            The position of the stage.

        Raises
        ------
        e : `serial.SerialException`
            Raised when serial port has a problem.
        """
        try:
            reply = self.commander.send("get pos")
            self.log.info(reply)
            status_dictionary = self.check_reply(reply)
            if status_dictionary:
                self.log.info("Position captured")
                return float(float(reply.data) / self.steps_conversion)
        except SerialException as e:
            self.log.error(e)
            self.log.info("Command for device timed out")
            raise e

    def retrieve_status(self):
        """Return the status of the LinearStage.

        Returns
        -------
        str
            The status of the LinearStage.

        Raises
        ------
        e : `serial.SerialException`
            Raised when the serial port has a problem.

        """
        self.log.debug("retrieve_status - starting")
        try:
            reply = self.commander.send("")
            self.log.info(reply)
            status_dictionary = self.check_reply(reply)
            if status_dictionary:
                self.log.info("retrieve_status - Status captured")
                return reply.device_status
        except SerialException as e:
            self.log.error(e)
            raise

    async def publish(self):
        """Publish the telemetry of the stage."""
        self.position = self.get_position()
        self.status = self.retrieve_status()

    async def stop(self):
        """Stop the movement of the stage.

        Raises
        ------
        e : `serial.SerialException`
            Raised when the serial port has a problem.
        """
        try:
            reply = self.commander.send("stop")
            self.log.debug(reply)
            status_dictionary = self.check_reply(reply)
            if status_dictionary:
                self.log.info("Device stopped")
        except SerialException as e:
            self.log.error(e)
            raise e