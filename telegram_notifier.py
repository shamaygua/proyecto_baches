import requests
from datetime import datetime

BOT_TOKEN = "8789667995:AAGOyk_qzBXDTKh1Q2WOg4fv3yTBX--bnCQ"
CHAT_ID = "5726772688"

def send_telegram_message(text: str) -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception:
        return False

def build_alert(title: str, message: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"{title}\nFecha y hora: {now}\n{message}"

if __name__ == "__main__":
    msg = build_alert(
        "✅ Prueba de Telegram",
        "El bot del sistema de detección de baches se configuró correctamente."
    )
    ok = send_telegram_message(msg)
    print("Mensaje enviado:", ok)
