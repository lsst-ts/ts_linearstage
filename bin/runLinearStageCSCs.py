from lsst.ts.linearStage.statemachine import LinearStageCSC
from salpytools import salpylib


def main():
    print("CSCs Starting")
    lsc = LinearStageCSC("/dev/ttyUSB0", 1)
    lsc2 = LinearStageCSC("/dev/ttyUSB0", 2)

    while True:
        pass


if __name__ == '__main__':
    main()
