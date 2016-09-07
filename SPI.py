from ctypes import *
import time
import math
from collections import namedtuple

SPI_PINS = namedtuple('SPI_PINS', 'MOSI, MISO, SCLK, SS')


class SPI():
    def __init__(self,pin_cfg=SPI_PINS(MOSI=0,MISO=1,SCLK=2,SS=3)):
        '''initialize dll, setup gpio pins as desired'''

        print("DWF library")
        dwf = cdll.dwf

        version = create_string_buffer(16)
        dwf.FDwfGetVersion(version)
        print("Version: {}".format(version.value))

        cdevices = c_int()
        dwf.FDwfEnum(c_int(0), byref(cdevices))
        print("Number of Devices: {}".format(cdevices.value))

        print("Opening first device")
        hdev = c_int()
        dwf.FDwfDeviceOpen(c_int(0), byref(hdev))


