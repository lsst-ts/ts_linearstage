import os
import pty
import serial
import threading


class Server:
    def __init__(self):
        self.master, self.slave = pty.openpty()
        self.commander = serial.Serial(os.ttyname(self.master))
        self.stop = False

    @property
    def s_name(self):
        return os.ttyname(self.slave)

    def start(self):
        self.serial_thread = threading.Thread(target=self.cmd_loop, args=[])
        self.serial_thread.start()

    def stop(self):
        self.stop = True
        self.serial_thread.join()

    def cmd_loop(self):
        while not self.stop:
            line = self.commander.read_until("\n")
            self.commander.write(line.encode())
