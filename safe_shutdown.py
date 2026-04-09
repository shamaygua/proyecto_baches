import RPi.GPIO as GPIO
import time
import os

BUTTON_PIN = 26
HOLD_TIME_SEC = 2.0

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print("Safe shutdown listo. Mantén pulsado el botón para apagar.")

press_start = None

try:
    while True:
        button_pressed = GPIO.input(BUTTON_PIN) == GPIO.LOW

        if button_pressed:
            if press_start is None:
                press_start = time.time()
            else:
                held_time = time.time() - press_start
                if held_time >= HOLD_TIME_SEC:
                    print("Botón mantenido. Ejecutando apagado seguro...")
                    os.system("sudo shutdown -h now")
                    break
        else:
            press_start = None

        time.sleep(0.1)

except KeyboardInterrupt:
    print("Script detenido manualmente.")

finally:
    GPIO.cleanup()
