# TODO: Add in Sphinx documentation
# TODO: Finish up docstrings
# TODO: Add module docstring
# TODO: Add in Unit Tests
# TODO: Add in XML
# TODO: Add in XML for commands
# TODO: Add in XML for events
# TODO: Add in XML for telemetry

from zaber.serial import AsciiSerial, AsciiDevice, AsciiCommand, AsciiReply
from zaber.serial.exceptions import TimeoutError
import logging
from serial import SerialException

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


class LinearStageComponent(AsciiDevice):
    """ """

    # TODO: Add class docstring
    def __init__(self, port: object, address: object) -> object:
        """

        :rtype: object
        :type port: AsciiSerial
        :type address: Int
        :param port: This is the serial port where the linear stage is located.
        :param address: This is the device address, typically incremental i.e. device 1 is 1.
        """
        try:
            super(LinearStageComponent, self).__init__(port, address)
        except SerialException as e:
            logger.error(e)
            logger.info("It is likely that this port is already being accessed by some other program.")
            raise
        logger.info("Connected to Linear Stage #{}".format(self.address))
        self.cmd_queue = LinearStageQueue()
        self.reply_queue = LinearStageQueue()
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
            "LOCKSTEP": "An axis cannot be moved using normal motion commands because it is part of a lockstep group.",
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
            "WT": "The internal temperature of the controller has exceeded the recommended limit for the device.",
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
        logger.debug("created LinearStageComponent")
        # TODO: Finish docstring

    def move_absolute(self, value):
        """This method moves the linear stage absolutely by the number of steps away from the starting position.
        i.e. value=10 would mean the stage would move 10 millimeters away from the start.
        
        The method uses a try-catch block to handle the Timeout error exception. It sends the command which returns a
        reply that is logged and then check for accepted or rejected status according to SAL specifications. If the
        command is accepted then the command begins executing. The device is polled for its status until the device is
        idle. If the command finishes successfully then it is logged and the position is set by the get_position
        function.

        Parameters
        ----------
        value :
            The number of millimeters(converted) to move the stage.

        Returns
        -------

        """
        try:
            reply = self.send("move abs {}".format(value*8000))
            logger.debug(reply)
            if self.check_reply(reply):
                logger.info("Device is moving {} millimeter(s) from home position".format(value))
                while self.get_status() != "IDLE":
                    logger.info("Device is moving... - SAL_INPROGRESS_301")
                logger.info("Device moved - SAL_COMPLETE_303")
                self.position = self.get_position()
                logger.debug(self.position)
        except TimeoutError as e:
            logger.error(e)
            logger.info("Command timeout - SAL_CMD_NOACK_-301")
            raise
        # TODO: Rewrite if statement to be every such X condition

    def move_relative(self, value):
        """This method moves the linear stage relative to the current position.
        
        This method begins by establishing a try-catch block which handles the timeout exception by logging the error
        and proper SAL code. The command is then sent to the device where a reply is ostensibly returned. The reply is
        checked for acknowledgement or rejection and handled accordingly. If the command is accepted the device will
        perform the move and poll the device until it is idle returning SAL codes. The position attribute is updated
        using the get_position function.

        Parameters
        ----------
        value :
            The number of millimeters to move the stage.

        Returns
        -------

        """
        try:
            reply = self.send("move rel {}".format(value * 8000))
            logger.info(reply)
            if self.check_reply(reply):
                logger.info("Device is being moved {} millimeters".format(value))
                while self.get_status() != "IDLE":
                    logger.info("Device is moving... - SAL_INPROGRESS_301")
                logger.info("Device moved - SAL_COMPLETE_303")
                self.position = self.get_position()
        except TimeoutError as e:
            logger.error(e)
            logger.info("Command timeout - SAL_CMD_NOACK_-301")
        # TODO: Change polling to every X rate

    def get_home(self):
        """This method calls the homing method of the device which is used to establish a reference position.
        
        The method begins by forming an AsciiCommand for the home command. The try-catch block is then established for
        the rest of the method in order to catch the timeout error and handle it appropriately. The command is sent to
        the device and a reply is likely returned. The reply is then checked for accepted or rejected status. If the
        command is accepted then the command begins to perform. The device is polled until idle while returning the
        appropriate SAL codes. If the command finishes successfully then the SAL code is logged.
        
        :return:

        Parameters
        ----------

        Returns
        -------

        """
        cmd = AsciiCommand("{} home".format(self.address))
        self.cmd_queue.push(cmd)
        try:
            reply = self.send(cmd)
            logger.info(reply)
            if self.check_reply(reply):
                logger.info("Device {} is homing - SAL_INPROGRESS_301".format(self.address))
                while self.get_status() != "IDLE":
                    logger.info("Device {} homing... - SAL_INPROGRESS_301".format(self.address))
                logger.info("Device {} is homed - SAL_COMPLETE_303".format(self.address))
        except SerialException as e:
            logger.error(e)
            logger.info("Command for device timed out - SAL_CMD_NOACK_-301")
            raise

    def check_reply(self, reply):
        """This method checks the reply for any warnings or errors and acknowledgement or rejection of the command.
        
        This method has 4 if-else clauses that it checks for any normal or abnormal operation of the linear stage.

        Parameters
        ----------
        reply :
            This is the reply that is to be checked.

        Returns
        -------

        """
        if reply.reply_flag == "RJ" and reply.warning_flag != "--":
            logger.warning("Command rejected by device {} for {}".format(
                self.address, self.warning_flag_dictionary[reply.warning_flag]))
            return False
        elif reply.reply_flag == "RJ" and reply.warning_flag == "--":
            logger.error("Command rejected due to {}".format(self.reply_flag_dictionary.get(reply.data, reply.data)))
            return False
        elif reply.reply_flag == "OK" and reply.warning_flag != "--":
            logger.warning("Command accepted but probably would return improper result due to {}".format(
                self.warning_flag_dictionary[reply.warning_flag]))
            return False
        else:
            logger.info("Command accepted by device #{} - SAL_ACKNOWLEDGED_300".format(self.address))
            return True

    def get_position(self):
        """This method returns the position of the linear stage.
        
        It works by sending a command to the device and ostensibly is given a reply. The reply is then checked for
        acceptance or rejection by the device and the position is then set by the return of the reply's data
        if successful.
        
        :return: The position of the linear stage

        Parameters
        ----------

        Returns
        -------

        """
        try:
            reply = self.send("get pos")
            logger.debug(reply)
            if self.check_reply(reply):
                logger.info("Position captured - SAL_EVENT_INFO_200")
                return reply.data
        except SerialException as e:
            logger.error(e)
            logger.info("Command for device timed out - SAL_CMD_NOACK_-301")
            raise


class LinearStageQueue:
    """ """
    # TODO: Finish LinearStageQueue class
    def __init__(self):
        self.items = []
        # TODO: Add docstring

    def push(self, item):
        """

        Parameters
        ----------
        item :
            

        Returns
        -------

        """
        self.items.append(item)
        # TODO: Add docstring

    def pop(self):
        """ """
        return self.items.pop()
        # TODO: Add docstring


def main():
    """ """
    ls_1 = LinearStageComponent(AsciiSerial("COM3"), 1)
    ls_1.move_absolute(4)
    ls_1.port.close()


if __name__ == '__main__':
    main()
