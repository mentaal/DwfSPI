from ctypes import *
import time
import math
import matplotlib.pyplot as plt

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


print("Configure and start first analog out channel")
dwf.FDwfAnalogOutEnableSet(hdev, c_int(0), c_int(1))
print("1 = Sine wave")
dwf.FDwfAnalogOutFunctionSet(hdev, c_int(0), c_int(1))
dwf.FDwfAnalogOutFrequencySet(hdev, c_int(0), c_double(3000))
print("")
dwf.FDwfAnalogOutConfigure(hdev, c_int(0), c_int(1))

print("Configure analog in")
dwf.FDwfAnalogInFrequencySet(hdev, c_double(1000000))
print("Set range for all channels")
dwf.FDwfAnalogInChannelRangeSet(hdev, c_int(-1), c_double(4))
dwf.FDwfAnalogInBufferSizeSet(hdev, c_int(1000))

print("Wait after first device opening the analog in offset to stabilize")
time.sleep(2)

print("Starting acquisition")
dwf.FDwfAnalogInConfigure(hdev, c_int(1), c_int(1))

print("   waiting to finish")
sts = c_int()
while True:
    dwf.FDwfAnalogInStatus(hdev, c_int(1), byref(sts))
    if sts.value == 2 :
        break
    time.sleep(0.1)
print("   done")


print("   reading data")
rg = (c_double*1000)()
dwf.FDwfAnalogInStatusData(hdev, c_int(0), rg, len(rg))

dwf.FDwfDeviceCloseAll()

dc = sum(rg)/len(rg)
print("DC: "+str(dc)+"V")


rgpy=[0.0]*len(rg)
for i in range(0,len(rgpy)):
    rgpy[i]=rg[i]

plt.plot(rgpy)
plt.show()

