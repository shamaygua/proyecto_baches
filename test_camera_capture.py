from picamera2 import Picamera2
import cv2
import time
import os

output_path = "/mnt/ssd/proyecto_baches/frames/test_camera.jpg"
os.makedirs(os.path.dirname(output_path), exist_ok=True)

picam2 = Picamera2()
config = picam2.create_preview_configuration(
    main={"size": (1280, 720), "format": "RGB888"}
)
picam2.configure(config)

try:
    picam2.start()
    time.sleep(2)
    frame = picam2.capture_array()
    cv2.imwrite(output_path, frame)
    print("Frame guardado en:", output_path)
finally:
    picam2.stop()
    picam2.close()
