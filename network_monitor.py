import time
import subprocess
from telegram_notifier import send_telegram_message, build_alert

CHECK_INTERVAL = 30  # segundos
PING_TARGET = "8.8.8.8"

internet_was_ok = True

def check_internet():
    try:
        result = subprocess.run(
            ["ping", "-c", "1", PING_TARGET],
            stdout=subprocess.DEVNULL
        )
        return result.returncode == 0
    except:
        return False

while True:
    internet_ok = check_internet()

    if internet_ok and not internet_was_ok:
        msg = build_alert(
            "Conexión restaurada",
            "El sistema recuperó conexión a internet."
        )
        send_telegram_message(msg)

    elif not internet_ok and internet_was_ok:
        msg = build_alert(
            "Sin conexión",
            "El sistema perdió conexión a internet."
        )
        send_telegram_message(msg)

    internet_was_ok = internet_ok

    time.sleep(CHECK_INTERVAL)
