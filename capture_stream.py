import os
import time
import argparse
from datetime import datetime

from picamera2 import Picamera2
import cv2

# =========================
# CONFIGURACIÓN
# =========================
CAPTURE_INTERVAL_SEC = 1.0
WIDTH = 640
HEIGHT = 480


def get_run_folder(output_root: str, run_id: str):
    path = os.path.join(output_root, f"run_{run_id}")
    os.makedirs(path, exist_ok=True)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=str, required=True, help="ID único de corrida")
    parser.add_argument(
        "--output-root",
        type=str,
        default="/mnt/ssd/proyecto_baches/frames",
        help="Directorio raíz de salida para frames"
    )
    args = parser.parse_args()

    run_folder = get_run_folder(args.output_root, args.run_id)
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
                print(f"Guardado: {filename} | run_id: {args.run_id}")

                last_capture_time = now

    except KeyboardInterrupt:
        print("\nCaptura detenida por usuario")

    finally:
        picam2.stop()
        picam2.close()


if __name__ == "__main__":
    main()
