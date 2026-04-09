import serial
import time
from datetime import datetime


class GpsReader:
    def __init__(self, port="/dev/rfcomm0", baudrate=9600, timeout=1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None

    def connect(self):
        while True:
            try:
                print(f"[GPS] Intentando conectar a {self.port}...")
                self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
                time.sleep(2)
                print("[GPS] Conectado correctamente")
                break
            except Exception as e:
                print(f"[GPS] Error de conexión: {e}")
                time.sleep(2)

    def read_line(self):
        try:
            line = self.ser.readline().decode("utf-8", errors="ignore").strip()
            return line
        except Exception:
            return None

    def parse_line(self, line):
        if not line or not line.startswith("GPS"):
            return None

        parts = line.split(",")

        if len(parts) < 7:
            return None

        try:
            seq = int(parts[1])
            millis = int(parts[2])
            status = parts[3]

            if status == "OK":
                lat = float(parts[4])
                lon = float(parts[5])
                sat = int(parts[6])
            else:
                lat = None
                lon = None
                sat = int(parts[6])

            return {
                "seq": seq,
                "millis": millis,
                "status": status,
                "lat": lat,
                "lon": lon,
                "sat": sat,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            }

        except Exception:
            return None

    def get_data(self):
        line = self.read_line()
        if not line:
            return None

        parsed = self.parse_line(line)
        return parsed


# prueba independiente
if __name__ == "__main__":
    gps = GpsReader()
    gps.connect()

    print("Leyendo datos GPS por Bluetooth...")

    while True:
        data = gps.get_data()
        if data:
            print(data)
