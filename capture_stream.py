import os
import time
from datetime import datetime

from picamera2 import Picamera2
import cv2

# =========================
# CONFIGURACIÓN
# =========================
CAPTURE_INTERVAL_SEC = 1.0   # guardar 1 frame cada 1 segundo
WIDTH = 640
HEIGHT = 480


def get_run_folder():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"/mnt/ssd/proyecto_baches/frames/run_{ts}"
    os.makedirs(path, exist_ok=True)
    return path


def main():
    run_folder = get_run_folder()
    print("Guardando frames en:", run_folder)

    picam2 = Picamera2()
    config = picam2.create_preview_configuration(
        main={"size": (WIDTH, HEIGHT), "format": "RGB888"}
    )
    picam2.configure(config)

    picam2.start()
    time.sleep(2)

    frame_count = 0
    last_capture_time = 0

    try:
        while True:
            now = time.time()

            if now - last_capture_time >= CAPTURE_INTERVAL_SEC:
                frame = picam2.capture_array()

                frame_count += 1
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                filename = f"frame_{frame_count:04d}_{ts}.jpg"
                filepath = os.path.join(run_folder, filename)

                cv2.imwrite(filepath, frame)

                print(f"Guardado: {filename} | ts: {ts}")

                last_capture_time = now

    except KeyboardInterrupt:
        print("\nCaptura detenida por usuario")

    finally:
        picam2.stop()
        picam2.close()


if __name__ == "__main__":
    main()
