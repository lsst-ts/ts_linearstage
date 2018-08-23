from lsst.ts.linearStage.ls import LinearStageComponent
from zaber.serial import AsciiReply
import pytest


class TestLinearStageComponent:

    @pytest.fixture(scope="class")
    def lsc(self):
        lsc = LinearStageComponent("/dev/ttyUSBlinearStage", 1)
        return lsc

    def test_connection(self,lsc):
        assert lsc is not None

    def test_enable(self,lsc):
        lsc.enable()
        assert lsc.port._ser.is_open is True

    def test_disable(self,lsc):
        lsc.disable()
        assert lsc.port._ser.is_open is False

    def test_command_accepted(self,lsc):
        reply = AsciiReply("@ 01 0 OK IDLE -- 0 \r")
        status_dictionary = lsc.check_reply(reply)
        assert status_dictionary == {'accepted': True, 'code': 0, 'message': "Done: OK"}

    def test_command_rejected_again(self,lsc):
        reply = AsciiReply("@ 01 0 RJ IDLE -- AGAIN \r")
        status_dictionary = lsc.check_reply(reply)
        assert status_dictionary == {'accepted': False, 'code': 3, 'message': lsc.reply_flag_dictionary[reply.data]}

    def test_command_rejected_badaxis(self,lsc):
        reply = AsciiReply("@ 01 0 RJ IDLE -- BADAXIS \r")
        status_dictionary = lsc.check_reply(reply)
        assert status_dictionary == {'accepted': False, 'code': 3, 'message': lsc.reply_flag_dictionary[reply.data]}
