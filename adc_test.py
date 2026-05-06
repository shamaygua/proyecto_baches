import time
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c)
ads.gain = 1

chan = AnalogIn(ads, 3)

DIVIDER_RATIO = (14.7 + 4.7) / 4.7

if __name__ == "__main__":
    print("Leyendo ADC...")
    while True:
        v_adc = chan.voltage
        v_bat = v_adc * DIVIDER_RATIO
        print(f"ADC: {v_adc:.3f} V | Batería: {v_bat:.3f} V")
        time.sleep(1)
