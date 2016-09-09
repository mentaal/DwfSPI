from ctypes import (cdll, c_int, c_long, byref, create_string_buffer,
                    c_double, c_uint, c_bool, c_byte)
from dwfconstants import *
import time
import math
from time import sleep
from collections import namedtuple
import logging
import sys

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

SPI_PINS = namedtuple('SPI_PINS', 'MOSI, MISO, SCLK, SS')


class SPI():
    '''simple class to bitbang spi on the digital Analog Discovery kit'''
    def __init__(self,
                 pin_cfg=SPI_PINS(MOSI=0,MISO=3,SCLK=1,SS=2),
                 CPOL=0,
                 CPHA=0,
                 speed=10e6):
        '''initialize dll and SPI configuration
        Note: setup times are probably not required as this library will likely
        be too slow to need them
        Args:
            pin_cfg (SPI_PINS): the pins on which you want to use SPI
            CPOL (int): SPI Polarity setting
            CPHA (int): SPI Phase setting
            speed (int): Speed of SPI clk in Hz
        '''
        #check pins
        pin_cfg_set = set(pin_cfg)
        if len(pin_cfg_set) != 4:
            raise ValueError("SPI pins need to be unique!")
        if max(pin_cfg_set) > 15:
            raise ValueError("SPI pin setting is out of range!")
        dwf = cdll.dwf
        self.speed = speed
        self.bit_period = 1/(speed)
        self.half_bit_period = self.bit_period/2
        self.pin_cfg = pin_cfg
        self.CPOL = CPOL
        self.CPHA = CPHA

        self.SS_mask   = 1 << self.pin_cfg.SS
        self.MOSI_mask = 1 << self.pin_cfg.MOSI
        self.MISO_mask = 1 << self.pin_cfg.MISO
        self.SCLK_mask = 1 << self.pin_cfg.SCLK



        version = create_string_buffer(16)
        dwf.FDwfGetVersion(version)
        logger.debug("Version: {}".format(version.value))

        cdevices = c_int()
        dwf.FDwfEnum(0, byref(cdevices))
        logger.debug("Number of Devices: {}".format(cdevices.value))

        logger.debug("Opening first device")
        hdwf = c_int()
        dwf.FDwfDeviceOpen(-1, byref(hdwf))
        if hdwf.value == hdwfNone.value:
            szerr = create_string_buffer(512)
            dwf.FDwfGetLastErrorMsg(szerr)
            logger.info(szerr.value)
            logger.fatal("failed to open device")
            sys.exit()

        self.hdwf = hdwf
        self.dwf = dwf

    def initialize_pins(self):
        '''setup gpio pins as desired'''
        ##reset all gpio pins
        #dwf = self.dwf
        dwf = self.dwf
        hdwf = self.hdwf
        dwf.FDwfDigitalIOReset(hdwf)
        bit_divider_ratio = self.setup_output(dwf, hdwf)
        self.setup_input(dwf, hdwf, bit_divider_ratio)


    def setup_output(self, dwf, hdwf):
        '''setup output pins'''
        hzSys = c_double()
        dwf.FDwfDigitalOutInternalClockInfo(hdwf, byref(hzSys))

        bit_divider_ratio = int(hzSys.value/self.speed)
        sclk_divider_ratio = int(hzSys.value/self.speed/2)
        ##set output enables for SPI pins
        #below doesn't work for some reason
        ##output_mask = self.MOSI_mask | self.SCLK_mask | self.SS_mask
        ##dwf.FDwfDigitalIOOutputEnableSet(hdwf, output_mask)

        # DIO 2 Select 
        dwf.FDwfDigitalOutEnableSet(hdwf, self.pin_cfg.SS, 1)
        # output high while DigitalOut not running
        dwf.FDwfDigitalOutIdleSet(hdwf, self.pin_cfg.SS, DwfDigitalOutIdleHigh) # 2=DwfDigitalOutIdleHigh
        # output constant low while running
        dwf.FDwfDigitalOutCounterInitSet(hdwf, self.pin_cfg.SS, 0, 0)
        dwf.FDwfDigitalOutCounterSet(hdwf, self.pin_cfg.SS, 0, 0)

        # DIO 1 Clock
        dwf.FDwfDigitalOutEnableSet(hdwf, self.pin_cfg.SCLK, 1)
        # set prescaler twice of SPI frequency
        dwf.FDwfDigitalOutDividerSet(hdwf, self.pin_cfg.SCLK, sclk_divider_ratio)
        # 1 tick low, 1 tick high
        dwf.FDwfDigitalOutCounterSet(hdwf, self.pin_cfg.SCLK, 1, 1)
        # start with low or high based on clock polarity
        dwf.FDwfDigitalOutCounterInitSet(hdwf, self.pin_cfg.SCLK, self.CPOL, 1)
        dwf.FDwfDigitalOutIdleSet(hdwf, self.pin_cfg.SCLK, 1+self.CPOL) # 1=DwfDigitalOutIdleLow 2=DwfDigitalOutIdleHigh

        # DIO 0 Data
        dwf.FDwfDigitalOutEnableSet(hdwf, self.pin_cfg.MOSI, 1)
        dwf.FDwfDigitalOutTypeSet(hdwf, self.pin_cfg.MOSI, DwfDigitalOutTypeCustom) # 1=DwfDigitalOutTypeCustom
        # for high active clock, hold the first bit for 1.5 periods 
        dwf.FDwfDigitalOutDividerInitSet(hdwf, self.pin_cfg.MOSI,
                int((1+0.5*self.CPHA)*bit_divider_ratio))
        # SPI frequency, bit frequency
        dwf.FDwfDigitalOutDividerSet(hdwf, self.pin_cfg.MOSI, bit_divider_ratio)
        dwf.FDwfDigitalOutIdleSet(hdwf, self.pin_cfg.MOSI, DwfDigitalOutIdleLow) # 1=DwfDigitalOutIdleLow 2=DwfDigitalOutIdleHigh

        return sclk_divider_ratio

    def setup_input(self, dwf, hdwf, sclk_divider_ratio):

        buff_max = c_int()
        dwf.FDwfDigitalInBufferSizeGet(hdwf, byref(buff_max))
        logger.debug("Maximum buffer size is: {}".format(buff_max))
        dwf.FDwfDigitalInAcquisitionModeSet(hdwf, acqmodeSingle)
        #setup data read currently in loopback
        #just read back what is being written to MOSI as a sanity check
        #sample rate = system frequency / divider, 100MHz/1
        dwf.FDwfDigitalInDividerSet(hdwf, sclk_divider_ratio) #sample on clk edge to accomodate for CPHA==1
        # 16bit per sample format
        dwf.FDwfDigitalInSampleFormatSet(hdwf, c_int(16))

        #dwf.FDwfDigitalInTriggerSourceSet(hdwf, trigsrcDigitalOut)
        dwf.FDwfDigitalInTriggerSourceSet(hdwf, trigsrcDigitalIn)
        #trigger on falling SS
        #dwf.FDwfDigitalInTriggerSet(hdwf, 0, 0, 0, self.SS_mask) #low, high, rising, falling
        if self.CPOL == 0 and self.CPHA == 0:
            dwf.FDwfDigitalInTriggerSet(hdwf, self.SS_mask, 0, self.SCLK_mask, 0) #low, high, rising, falling
        elif self.CPOL == 0 and self.CPHA == 1:
            dwf.FDwfDigitalInTriggerSet(hdwf, self.SS_mask, 0, 0, self.SCLK_mask) #low, high, rising, falling
        elif self.CPOL == 1 and self.CPHA == 0:
            dwf.FDwfDigitalInTriggerSet(hdwf, self.SS_mask, 0, self.SCLK_mask, 0) #low, high, rising, falling
        elif self.CPOL == 1 and self.CPHA == 1:
            dwf.FDwfDigitalInTriggerSet(hdwf, self.SS_mask, 0, 0, self.SCLK_mask) #low, high, rising, falling




    def write(self, byte_array:bytes, lsb_tx_first=False, lsb_rx_first=False) -> bytes:
        '''write an integer word and return the read back value'''
        sts = c_byte()
        dwf = self.dwf
        hdwf = self.hdwf
        byte_count = len(byte_array)
        bit_count = byte_count*8
        sample_count = bit_count*2+2 #sample at clock freq to cater for cpha
        #logger.info('bit_count: {}'.format(bit_count))
        # serialization time length
        dwf.FDwfDigitalOutRunSet(hdwf, c_double((bit_count+0.4)/self.speed))

        dwf.FDwfDigitalInTriggerSourceSet(hdwf, trigsrcDigitalOut)
        #trigger on falling SS
        dwf.FDwfDigitalInTriggerSet(hdwf, 0, 0, 0, self.SS_mask) #low, high, rising, falling
        # set number of sample to acquire
        dwf.FDwfDigitalInBufferSizeSet(hdwf, sample_count)
        # number of samples after trigger
        dwf.FDwfDigitalInTriggerPositionSet(hdwf, sample_count)
        #skip first sample as it occurs on active edge of SS

        if lsb_tx_first:
            data = (c_byte*byte_count)(*byte_array)
        else:
            new_bytes = []
            for i,b in enumerate(byte_array):
                new_byte = 0
                for bit_pos in range(8):
                    new_byte |= ((b >> bit_pos)&1) << (7- bit_pos) #reorder bits
                new_bytes.append(new_byte)
            data = (c_byte*byte_count)(*new_bytes)

        #data = bs
        dwf.FDwfDigitalOutDataSet(hdwf, self.pin_cfg.MOSI, byref(data), bit_count)
        # begin acquisition
        dwf.FDwfDigitalInConfigure(hdwf, 0, 1) #reconfigure, start acquisition
        #dwf.FDwfDigitalInStatus(hdwf, 1, byref(sts))
        ##logger.info("STS VAL: {}".format(sts.value))
        #assert sts.value == stsArm.value


        dwf.FDwfDigitalOutConfigure(hdwf, 1)


        while True:
            dwf.FDwfDigitalInStatus(hdwf, 1, byref(sts))
            #logger.info("STS VAL: {}".format(sts.value))
            if sts.value == stsDone.value :
                break
            time.sleep(0.001)
        #logger.info("Acquisition finished")

        # get samples, byte size
        rgwSamples = (c_uint16*sample_count)()
        dwf.FDwfDigitalInStatusData(hdwf, byref(rgwSamples), 2*sample_count)


        byte_array = []

        b = 0
        #logger.debug("Number of samples collected: {}".format(len(rgwSamples)))
        #for i, sample in enumerate(rgwSamples):
        #    rx_bit = (sample>>self.pin_cfg.MISO)&1
        #    logger.info("Sample {:2}: {:2}, mosi: {}, miso: {}".format(i, sample,
        #        (sample>>self.pin_cfg.MOSI)&1,
        #        rx_bit))

        Slice = rgwSamples[:bit_count*2:2]
        for i, sample in enumerate(Slice):
            i_mod_8 = i%8
            if i_mod_8==0 and i!=0: #new byte is ready
                byte_array.append(b)
                b = 0
            rx_bit = (sample>>self.pin_cfg.MISO)&1
            if lsb_rx_first:
                b |= rx_bit << i_mod_8
            else:
                b <<= 1
                b |= rx_bit
        #    logger.info("Sample {:2}: {:2}, mosi: {}, miso: {}".format(i, sample,
        #        (sample>>self.pin_cfg.MOSI)&1,
        #        rx_bit))
        byte_array.append(b)
        #logger.info("Returning: {}".format(byte_array))
        return byte_array



    def __del__(self):
        self.dwf.FDwfDigitalOutReset(self.hdwf);
        self.dwf.FDwfDeviceCloseAll()

if __name__ == '__main__':

    import random
    pin_cfg=SPI_PINS(MOSI=0,MISO=3,SCLK=1,SS=2)
    print(pin_cfg)
    #warning - timings for cpha=1 are off...retrieved data is unreliable!
    spi = SPI(pin_cfg=pin_cfg, CPHA=0, CPOL=0)
    spi.initialize_pins()


    #below test assumes that MOSI is tied to MISO physically
    for i in range(100):
        num = random.randint(0,255)
        returned = spi.write(bytes([num]), lsb_rx_first=False)
        assert returned == [num]
    #check a long packet
    nums = (random.randint(0,22) for i in range(100))
    to_write = bytes(nums)
    #print("to_write: {}".format(to_write))
    returned = spi.write(to_write)
    #print(returned)
    assert returned == list(to_write)
    ##print('returned: {}'.format(returned))
