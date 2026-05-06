import time
import os

from adc_test import chan, DIVIDER_RATIO
from telegram_notifier import send_telegram_message, build_alert

LOW_THRESHOLD = 11.1
CRITICAL_THRESHOLD = 10.6
CHECK_INTERVAL_SEC = 10
CRITICAL_CONFIRMATIONS = 3

low_alert_sent = False
critical_alert_sent = False
critical_counter = 0

print("Monitoreo de batería iniciado...\n")

while True:
    try:
        v_adc = chan.voltage
        v_bat = v_adc * DIVIDER_RATIO

        print(f"Batería: {v_bat:.2f} V")

        # Alerta de batería baja
        if v_bat < LOW_THRESHOLD and not low_alert_sent:
            msg = build_alert(
                "Batería baja",
                f"Voltaje detectado: {v_bat:.2f} V"
            )
            ok = send_telegram_message(msg)
            print("Alerta baja enviada:", ok)
            low_alert_sent = True

        # Confirmación de batería crítica
        if v_bat < CRITICAL_THRESHOLD:
            critical_counter += 1
            print(f"[WARN] Lectura crítica {critical_counter}/{CRITICAL_CONFIRMATIONS}")
        else:
            critical_counter = 0

        # Apagado seguro por batería crítica confirmada
        if critical_counter >= CRITICAL_CONFIRMATIONS and not critical_alert_sent:
            msg = build_alert(
                "Batería crítica",
                f"Voltaje detectado: {v_bat:.2f} V\nSe ejecutará apagado seguro."
            )
            ok = send_telegram_message(msg)
            print("Alerta crítica enviada:", ok)
            critical_alert_sent = True

            print("[INFO] Sincronizando escritura a disco...")
            os.system("sync")
            time.sleep(1)

            print("[INFO] Ejecutando apagado seguro...")
            os.system("sudo shutdown -h now")
            break

    except Exception as e:
        print(f"[ERROR][BATTERY_MONITOR] {e}")

    time.sleep(CHECK_INTERVAL_SEC)
