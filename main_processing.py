import sys
import os
import json
import argparse

sys.path.append('/home/sha/VL53L0X_rasp_python/python')
sys.path.append('/home/sha/proyecto_baches')
os.chdir('/home/sha/VL53L0X_rasp_python/python')

import time
from datetime import datetime
import VL53L0X
import RPi.GPIO as GPIO
import smbus2 as smbus

from utils.filter import MedianFilter, MovingAverageFilter, OffsetCompensator
from sensors.gps_reader import GpsReader

# =========================
# CONFIGURACIÓN TOF
# =========================
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

# =========================
# CONFIGURACIÓN IMU
# =========================
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

def timestamp_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def read_imu_raw():
    ax_raw = read_word(0x3B)
    ay_raw = read_word(0x3D)
    az_raw = read_word(0x3F)

    gx_raw = read_word(0x43)
    gy_raw = read_word(0x45)
    gz_raw = read_word(0x47)

    return ax_raw, ay_raw, az_raw, gx_raw, gy_raw, gz_raw

def convert_imu(ax_raw, ay_raw, az_raw, gx_raw, gy_raw, gz_raw):
    ax = ax_raw / 16384.0
    ay = ay_raw / 16384.0
    az = -(az_raw / 16384.0)

    gx = gx_raw / 131.0
    gy = gy_raw / 131.0
    gz = gz_raw / 131.0

    return ax, ay, az, gx, gy, gz

# =========================
# ARGUMENTO DE NOMBRE DE CORRIDA
# =========================
parser = argparse.ArgumentParser()
parser.add_argument("--run-name", type=str, default="sensor_log")
args = parser.parse_args()

# =========================
# RUTA DE SALIDA
# =========================
output_dir = "/mnt/ssd/proyecto_baches/processed"
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, f"{args.run_name}.jsonl")

# =========================
# FILTROS TOF
# =========================
tof1_filter = MedianFilter(window_size=5)
tof2_filter = MedianFilter(window_size=5)

# =========================
# CALIBRACIÓN INICIAL IMU
# =========================
print("Calibrando IMU... deja el sistema quieto unos segundos")

cal_samples = 100
sum_ax = 0.0
sum_ay = 0.0
sum_az = 0.0
sum_gx = 0.0
sum_gy = 0.0
sum_gz = 0.0

time.sleep(2)

for _ in range(cal_samples):
    ax_raw, ay_raw, az_raw, gx_raw, gy_raw, gz_raw = read_imu_raw()
    ax, ay, az, gx, gy, gz = convert_imu(ax_raw, ay_raw, az_raw, gx_raw, gy_raw, gz_raw)

    sum_ax += ax
    sum_ay += ay
    sum_az += az
    sum_gx += gx
    sum_gy += gy
    sum_gz += gz

    time.sleep(0.02)

ax_offset = sum_ax / cal_samples
ay_offset = sum_ay / cal_samples
az_offset = sum_az / cal_samples
gx_offset = sum_gx / cal_samples
gy_offset = sum_gy / cal_samples
gz_offset = sum_gz / cal_samples

print("Offsets calculados:")
print(f"AX={ax_offset:.4f}, AY={ay_offset:.4f}, AZ={az_offset:.4f}, GX={gx_offset:.4f}, GY={gy_offset:.4f}, GZ={gz_offset:.4f}")

# =========================
# FILTROS IMU
# =========================
ax_offset_filter = OffsetCompensator(ax_offset)
ay_offset_filter = OffsetCompensator(ay_offset)
az_offset_filter = OffsetCompensator(az_offset)

gx_offset_filter = OffsetCompensator(gx_offset)
gy_offset_filter = OffsetCompensator(gy_offset)
gz_offset_filter = OffsetCompensator(gz_offset)

ax_avg_filter = MovingAverageFilter(window_size=5)
ay_avg_filter = MovingAverageFilter(window_size=5)
az_avg_filter = MovingAverageFilter(window_size=5)

gx_avg_filter = MovingAverageFilter(window_size=5)
gy_avg_filter = MovingAverageFilter(window_size=5)
gz_avg_filter = MovingAverageFilter(window_size=5)

# =========================
# GPS READER
# =========================
gps_reader = GpsReader(port="/dev/rfcomm0", baudrate=9600)
gps_reader.connect()
# =========================
# UMBRALES PRELIMINARES
# =========================
DELTA_TOF_UMBRAL_MM = 15
AZ_UMBRAL_G = 0.015
GYRO_APOYO_UMBRAL_DPS = 0.8

# Persistencia para cierre de evento
EVENT_END_DELAY_MS = 300

# =========================
# ESTADO TOF
# =========================
prev_tof1_filt = None
prev_tof2_filt = None

# =========================
# ESTADO EVENTOS
# =========================
current_event_id = 0
event_active_state = False
last_event_true_time = None

print("Procesamiento iniciado...")
print("timestamp | tof1_f | tof2_f | az_f | tof1_ev | tof2_ev | imu_v | cand | active | event_id | type")

try:
    with open(output_file, "a", encoding="utf-8") as f:
        while True:
            ts = timestamp_now()
            now_monotonic = time.monotonic()

            # GPS
            
            gps_data = gps_reader.get_data()
            # TOF
            d1_raw = tof1.get_distance()
            d2_raw = tof2.get_distance()

            d1_filt = tof1_filter.update(d1_raw)
            d2_filt = tof2_filter.update(d2_raw)

            delta_tof1 = None
            delta_tof2 = None

            if prev_tof1_filt is not None and d1_filt is not None:
                delta_tof1 = abs(d1_filt - prev_tof1_filt)

            if prev_tof2_filt is not None and d2_filt is not None:
                delta_tof2 = abs(d2_filt - prev_tof2_filt)

            prev_tof1_filt = d1_filt
            prev_tof2_filt = d2_filt

            evento_tof1 = delta_tof1 is not None and delta_tof1 >= DELTA_TOF_UMBRAL_MM
            evento_tof2 = delta_tof2 is not None and delta_tof2 >= DELTA_TOF_UMBRAL_MM
            evento_tof = evento_tof1 or evento_tof2
            evento_tof_ambos = evento_tof1 and evento_tof2

            if evento_tof_ambos:
                tof_zone = "ambos_lados"
            elif evento_tof1:
                tof_zone = "lado_1"
            elif evento_tof2:
                tof_zone = "lado_2"
            else:
                tof_zone = "ninguno"

            # IMU
            ax_raw, ay_raw, az_raw, gx_raw, gy_raw, gz_raw = read_imu_raw()
            ax, ay, az, gx, gy, gz = convert_imu(ax_raw, ay_raw, az_raw, gx_raw, gy_raw, gz_raw)

            ax_comp = ax_offset_filter.update(ax)
            ay_comp = ay_offset_filter.update(ay)
            az_comp = az_offset_filter.update(az)

            gx_comp = gx_offset_filter.update(gx)
            gy_comp = gy_offset_filter.update(gy)
            gz_comp = gz_offset_filter.update(gz)

            ax_filt = ax_avg_filter.update(ax_comp)
            ay_filt = ay_avg_filter.update(ay_comp)
            az_filt = az_avg_filter.update(az_comp)

            gx_filt = gx_avg_filter.update(gx_comp)
            gy_filt = gy_avg_filter.update(gy_comp)
            gz_filt = gz_avg_filter.update(gz_comp)

            evento_imu_vertical = az_filt is not None and abs(az_filt) >= AZ_UMBRAL_G

            evento_gyro_apoyo = False
            if gx_filt is not None and abs(gx_filt) >= GYRO_APOYO_UMBRAL_DPS:
                evento_gyro_apoyo = True
            if gy_filt is not None and abs(gy_filt) >= GYRO_APOYO_UMBRAL_DPS:
                evento_gyro_apoyo = True
            if gz_filt is not None and abs(gz_filt) >= GYRO_APOYO_UMBRAL_DPS:
                evento_gyro_apoyo = True

            # Señal instantánea
            evento_candidato = evento_tof or evento_imu_vertical

            # Tipo instantáneo
            if evento_tof and evento_imu_vertical:
                instant_event_type = "bache_candidato_fuerte"
            elif evento_tof:
                instant_event_type = "evento_geometrico"
            elif evento_imu_vertical:
                instant_event_type = "evento_vertical"
            else:
                instant_event_type = "normal"

            if instant_event_type != "normal" and evento_gyro_apoyo:
                instant_event_type = instant_event_type + "_con_apoyo_gyro"

            # =========================
            # PERSISTENCIA DE EVENTO
            # =========================
            event_started = False

            if evento_candidato:
                last_event_true_time = now_monotonic

                if not event_active_state:
                    current_event_id += 1
                    event_active_state = True
                    event_started = True
            else:
                if event_active_state and last_event_true_time is not None:
                    elapsed_ms = (now_monotonic - last_event_true_time) * 1000.0
                    if elapsed_ms >= EVENT_END_DELAY_MS:
                        event_active_state = False

            event_active = event_active_state
            event_id = current_event_id if event_active else None

            # Si el evento sigue activo por persistencia aunque la señal instantánea haya caído,
            # mantenemos el tipo más simple de continuidad
            if event_active:
                event_level = instant_event_type if instant_event_type != "normal" else "evento_en_cierre"
            else:
                event_level = "normal"

            sample = {
                "timestamp": ts,

                "tof1_raw_mm": d1_raw,
                "tof1_filt_mm": d1_filt,
                "tof2_raw_mm": d2_raw,
                "tof2_filt_mm": d2_filt,

                "delta_tof1_mm": delta_tof1,
                "delta_tof2_mm": delta_tof2,

                "evento_tof1": evento_tof1,
                "evento_tof2": evento_tof2,
                "evento_tof": evento_tof,
                "evento_tof_ambos": evento_tof_ambos,
                "tof_zone": tof_zone,

                "ax_raw_g": ax,
                "ay_raw_g": ay,
                "az_raw_g": az,
                "gx_raw_dps": gx,
                "gy_raw_dps": gy,
                "gz_raw_dps": gz,

                "ax_filt_g": ax_filt,
                "ay_filt_g": ay_filt,
                "az_filt_g": az_filt,
                "gx_filt_dps": gx_filt,
                "gy_filt_dps": gy_filt,
                "gz_filt_dps": gz_filt,

                "evento_imu_vertical": evento_imu_vertical,
                "evento_gyro_apoyo": evento_gyro_apoyo,

                "evento_candidato": evento_candidato,
                "instant_event_type": instant_event_type,

                "event_active": event_active,
                "event_id": event_id,
                "event_started": event_started,
                "event_level": event_level,

                "gps_status": gps_data["status"] if gps_data else None,
		"lat": gps_data["lat"] if gps_data else None,
		"lon": gps_data["lon"] if gps_data else None,
		"sat": gps_data["sat"] if gps_data else None,
		"gps_timestamp": gps_data["timestamp"] if gps_data else None,
		"gps_seq": None,
		"arduino_ms": None,
		"rpi_rx_ts": None,
		"gps_age_ms": None,
                "gps_usable": True if gps_data and gps_data["status"] == "OK" else False
            }

            print(
                f"{sample['timestamp']} | "
                f"{sample['tof1_filt_mm']} | {sample['tof2_filt_mm']} | "
                f"{sample['az_filt_g']:.3f} | "
                f"{sample['evento_tof1']} | {sample['evento_tof2']} | "
                f"{sample['evento_imu_vertical']} | {sample['evento_candidato']} | "
                f"{sample['event_active']} | {sample['event_id']} | "
                f"{sample['event_level']}"
            )

            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
            f.flush()

            time.sleep(0.1)

except KeyboardInterrupt:
    print("Detenido")

finally:
    tof1.stop_ranging()
    tof2.stop_ranging()
    GPIO.cleanup()
