""" This module is for the Zaber linear stage component according to SAL specifications

"""

# TODO: Add in Sphinx documentation
# TODO: Finish up docstrings
# TODO: Add module docstring
# TODO: Add in Unit Tests

from zaber import serial as zaber
import logging
from serial import SerialException
import time


class LinearStageComponent(zaber.AsciiDevice):
    """A class representing the linear stage device

    Parameters
    ----------

    port :
        The serial port that the device is connected.

    address :
        The address of the device, typically 1 or 2 in this use case.

    Attributes
    ----------
    reply_queue : LinearStageQueue
        A queue designed to hold replies connected to commands

    position : str
        This holds the position of the linear stage. It starts at none as
        device requires homing to be done before it can be moved.

    reply_flag_dictionary : dict
        This is a dictionary which contains all of the reply flags
        corresponding to what they mean.

    warning_flag_dictionary : dict
        This is a dictionary which contains all of the warning flags which correspond to what those flags
        mean.

     """

    def __init__(self, port: str, address: int) -> None:
        self.logger = logging.getLogger(__name__)
        self.serial_port = port
        self.device_address = address
        self.address = 1
        self.position = None
        self.reply_flag_dictionary = {
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
                          "because it is currently busy."
        }
        self.warning_flag_dictionary = {
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
                  "is unsupported by the current peripheralid.",
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
            "NJ": "Joystick calibration is in progress. Moving the joystick will have no effect."
        }
        self.logger.debug("created LinearStageComponent")

    def move_absolute(self, value):
        """This method moves the linear stage absolutely by the number of steps away from the starting
        position. i.e. value=10 would mean the stage would move 10 millimeters away from the start.

        The method uses a try-catch block to handle the Timeout error exception. It sends the command which
        returns a reply that is logged and then check for accepted or rejected status according to SAL
        specifications. If the command is accepted then the command begins executing. The device is polled for
        its status until the device is idle. If the command finishes successfully then it is logged and the
        position is set by the get_position function.

        Parameters
        ----------
        value :
            The number of millimeters(converted) to move the stage.

        Returns
        -------

        """
        try:
            reply = self.send("move abs {}".format(int(value*8000)))
            self.logger.debug(reply)
            self.check_reply(reply)
        except TimeoutError as e:
            self.logger.error(e)
            self.logger.info("Command timeout")
            raise

    def move_relative(self, value):
        """This method moves the linear stage relative to the current position.

        This method begins by establishing a try-catch block which handles the timeout exception by logging
        the error and proper SAL code. The command is then sent to the device where a reply is ostensibly
        returned. The reply is checked for acknowledgement or rejection and handled accordingly. If the
        command is accepted the device will perform the move and poll the device until it is idle
        returning SAL codes. The position attribute is updated using the get_position function.

        Parameters
        ----------
        value :
            The number of millimeters(converted) to move the stage.

        Returns
        -------

        """
        try:
            self.logger.debug("move rel {}".format(int(value * 8000)))
            reply = self.send("move rel {}".format(int(value * 8000)))
            self.logger.info(reply)
            self.check_reply(reply)

        except TimeoutError as e:
            self.logger.error(e)
            self.logger.info("Command timeout")
            raise

    def get_home(self):
        """This method calls the homing method of the device which is used to establish a reference position.

        The method begins by forming an AsciiCommand for the home command. The try-catch block is then
        established for the rest of the method in order to catch the timeout error and handle it
        appropriately. The command is sent to the device and a reply is likely returned. The reply is then
        checked for accepted or rejected status. If the command is accepted then the command begins to
        perform. The device is polled until idle while returning the appropriate SAL codes. If the command
        finishes successfully then the SAL code is logged.

        Parameters
        ----------

        Returns
        -------

        """
        cmd = zaber.AsciiCommand("{} home".format(self.address))
        try:
            reply = self.send(cmd)
            self.logger.info(reply)
            self.check_reply(reply)
        except SerialException as e:
            self.logger.error(e)
            self.logger.info("Command for device timed out")
            raise

    def check_reply(self, reply):
        """This method checks the reply for any warnings or errors and acknowledgement or rejection of the
        command.

        This method has 4 if-else clauses that it checks for any normal or abnormal operation of the linear
        stage.

        Parameters
        ----------
        reply :
            This is the reply that is to be checked.

        Returns
        -------

        """
        if reply.reply_flag == "RJ" and reply.warning_flag != "--":
            self.logger.warning("Command rejected by device {} for {}".format(
                self.address, self.warning_flag_dictionary[reply.warning_flag]))
            return False
        elif reply.reply_flag == "RJ" and reply.warning_flag == "--":
            self.logger.error("Command rejected due to {}".format(
                self.reply_flag_dictionary.get(reply.data, reply.data)))
            return False
        elif reply.reply_flag == "OK" and reply.warning_flag != "--":
            self.logger.warning("Command accepted but probably would return improper result due to {}".format(
                self.warning_flag_dictionary[reply.warning_flag]))

            return True
        else:
            self.logger.info("Command accepted by device #{}".format(self.address))
            return True

    def get_position(self):
        """This method returns the position of the linear stage.

        It works by sending a command to the device and ostensibly is given a reply. The reply is then checked
        for acceptance or rejection by the device and the position is then set by the return of the reply's
        data if successful.

        Parameters
        ----------

        Returns
        -------

        """
        try:
            reply = self.send("get pos")
            self.logger.debug(reply)
            status_dictionary = self.check_reply(reply)
            if status_dictionary:
                self.logger.info("Position captured")
                return float(float(reply.data) / 8000)
        except SerialException as e:
            self.logger.error(e)
            self.logger.info("Command for device timed out")
            raise e

    def enable(self):
        super(LinearStageComponent, self).__init__(zaber.AsciiSerial(self.serial_port), self.device_address)
        self.port.open()
        self.logger.info("port opened")

    def disable(self):
        self.port.close()
        self.logger.info("port closed.")

    def retrieve_status(self):
        try:
            reply = self.send("")
            self.logger.debug(reply)
            status_dictionary = self.check_reply(reply)
            if status_dictionary:
                self.logger.info("Status captured")
                return reply.device_status
        except SerialException as e:
            self.logger.error(e)
            raise

    def stop(self):
        try:
            reply = self.send("stop")
            self.logger.debug(reply)
            status_dictionary = self.check_reply(reply)
            if status_dictionary:
                self.logger.info("Device stopped")
        except SerialException as e:
            self.logger.error(e)
            raise e


class MockLinearStageComponent:
    def __init__(self):
        self.position = 35
        self.status = "IDLE"
        self.max_limit = 75
        self.min_limit = 0

    def get_position(self):
        return self.position

    def get_status(self):
        return self.status

    def get_home(self):
        while self.position != 0:
            self.position -= 0.1
            time.sleep(0.01)

    def move_relative(self, value):
        while self.position != value:
            if value > 0:
                self.position += 0.1
            else:
                self.position -= 0.1
            time.sleep(0.01)

    def move_absolute(self, value):
        while self.position != value:
            if value > 0:
                self.position += 0.1
            else:
                self.position -= 0.1
            time.sleep(0.01)


def main():
    """ """
    ls_1 = LinearStageComponent("/dev/ttyUSB0", 1)
    ls_1.get_home()


if __name__ == '__main__':
    main()
