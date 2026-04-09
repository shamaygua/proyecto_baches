import sys
import os

sys.path.append('/home/sha/VL53L0X_rasp_python/python')
os.chdir('/home/sha/VL53L0X_rasp_python/python')

import time
from datetime import datetime
import VL53L0X
import RPi.GPIO as GPIO
import smbus

sensor1_shutdown = 17
sensor2_shutdown = 27

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

GPIO.setup(sensor1_shutdown, GPIO.OUT)
GPIO.setup(sensor2_shutdown, GPIO.OUT)

GPIO.output(sensor1_shutdown, GPIO.LOW)
GPIO.output(sensor2_shutdown, GPIO.LOW)
time.sleep(0.5)

tof1 = VL53L0X.VL53L0X(address=0x2B)
tof2 = VL53L0X.VL53L0X(address=0x2D)

GPIO.output(sensor1_shutdown, GPIO.HIGH)
time.sleep(0.5)
tof1.start_ranging(VL53L0X.VL53L0X_BETTER_ACCURACY_MODE)

GPIO.output(sensor2_shutdown, GPIO.HIGH)
time.sleep(0.5)
tof2.start_ranging(VL53L0X.VL53L0X_BETTER_ACCURACY_MODE)

bus = smbus.SMBus(1)
address = 0x68
bus.write_byte_data(address, 0x6B, 0)

def read_word(reg):
    high = bus.read_byte_data(address, reg)
    low = bus.read_byte_data(address, reg + 1)
    val = (high << 8) + low
    if val >= 0x8000:
        val = -((65535 - val) + 1)
    return val

def ts():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

print("timestamp | tof1 | tof2 | ax | ay | az | gx | gy | gz")

try:
    while True:
        t = ts()

        d1 = tof1.get_distance()
        d2 = tof2.get_distance()

        ax = read_word(0x3B) / 16384.0
        ay = read_word(0x3D) / 16384.0
        az = -(read_word(0x3F) / 16384.0)

        gx = read_word(0x43) / 131.0
        gy = read_word(0x45) / 131.0
        gz = read_word(0x47) / 131.0

        print(f"{t} | {d1} | {d2} | {ax:.3f} | {ay:.3f} | {az:.3f} | {gx:.3f} | {gy:.3f} | {gz:.3f}")

        time.sleep(0.1)

except KeyboardInterrupt:
    print("Detenido")

finally:
    tof1.stop_ranging()
    tof2.stop_ranging()
    GPIO.cleanup()
