import json
import os
import argparse
from datetime import datetime


def parse_ts(ts):
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")


def build_events(input_file):
    events = {}
    order = []

    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)

            event_id = data.get("event_id")

            if event_id is None:
                continue

            if event_id not in events:
                events[event_id] = {
                    "event_id": event_id,
                    "start_ts": data["timestamp"],
                    "end_ts": data["timestamp"],
                    "duration_ms": 0,

                    "event_level": data.get("event_level"),
                    "instant_event_type": data.get("instant_event_type"),
                    "tof_zone": data.get("tof_zone"),

                    "max_abs_az_filt_g": 0.0,
                    "max_abs_gx_filt_dps": 0.0,
                    "max_abs_gy_filt_dps": 0.0,
                    "max_abs_gz_filt_dps": 0.0,

                    "max_delta_tof1_mm": 0.0,
                    "max_delta_tof2_mm": 0.0,

                    "evento_tof1_detected": False,
                    "evento_tof2_detected": False,
                    "evento_tof_ambos_detected": False,
                    "evento_imu_vertical_detected": False,
                    "evento_gyro_apoyo_detected": False,

                    "gps_status": data.get("gps_status"),
                    "lat": data.get("lat"),
                    "lon": data.get("lon"),
                    "sat": data.get("sat"),
                    "gps_seq": data.get("gps_seq"),
                    "arduino_ms": data.get("arduino_ms"),
                    "rpi_rx_ts": data.get("rpi_rx_ts"),
                    "gps_age_ms": data.get("gps_age_ms"),
                    "gps_usable": data.get("gps_usable")
                }
                order.append(event_id)

            e = events[event_id]

            # actualizar tiempo final
            e["end_ts"] = data["timestamp"]

            # actualizar métricas máximas
            az = abs(data.get("az_filt_g") or 0.0)
            gx = abs(data.get("gx_filt_dps") or 0.0)
            gy = abs(data.get("gy_filt_dps") or 0.0)
            gz = abs(data.get("gz_filt_dps") or 0.0)

            d1 = data.get("delta_tof1_mm") or 0.0
            d2 = data.get("delta_tof2_mm") or 0.0

            if az > e["max_abs_az_filt_g"]:
                e["max_abs_az_filt_g"] = az
            if gx > e["max_abs_gx_filt_dps"]:
                e["max_abs_gx_filt_dps"] = gx
            if gy > e["max_abs_gy_filt_dps"]:
                e["max_abs_gy_filt_dps"] = gy
            if gz > e["max_abs_gz_filt_dps"]:
                e["max_abs_gz_filt_dps"] = gz

            if d1 > e["max_delta_tof1_mm"]:
                e["max_delta_tof1_mm"] = d1
            if d2 > e["max_delta_tof2_mm"]:
                e["max_delta_tof2_mm"] = d2

            # banderas acumuladas
            if data.get("evento_tof1"):
                e["evento_tof1_detected"] = True
            if data.get("evento_tof2"):
                e["evento_tof2_detected"] = True
            if data.get("evento_tof_ambos"):
                e["evento_tof_ambos_detected"] = True
            if data.get("evento_imu_vertical"):
                e["evento_imu_vertical_detected"] = True
            if data.get("evento_gyro_apoyo"):
                e["evento_gyro_apoyo_detected"] = True

            # actualizar nivel/tipo si aparece algo más fuerte después
            e["event_level"] = data.get("event_level", e["event_level"])
            e["instant_event_type"] = data.get("instant_event_type", e["instant_event_type"])
            e["tof_zone"] = data.get("tof_zone", e["tof_zone"])

            # GPS: conserva el último dato disponible del evento
            e["gps_status"] = data.get("gps_status", e["gps_status"])
            e["lat"] = data.get("lat", e["lat"])
            e["lon"] = data.get("lon", e["lon"])
            e["sat"] = data.get("sat", e["sat"])
            e["gps_seq"] = data.get("gps_seq", e["gps_seq"])
            e["arduino_ms"] = data.get("arduino_ms", e["arduino_ms"])
            e["rpi_rx_ts"] = data.get("rpi_rx_ts", e["rpi_rx_ts"])
            e["gps_age_ms"] = data.get("gps_age_ms", e["gps_age_ms"])
            e["gps_usable"] = data.get("gps_usable", e["gps_usable"])

    # calcular duración
    for eid in events:
        e = events[eid]
        t0 = parse_ts(e["start_ts"])
        t1 = parse_ts(e["end_ts"])
        e["duration_ms"] = int((t1 - t0).total_seconds() * 1000)

    return [events[eid] for eid in order]


def save_events(events, output_file):
    out_dir = os.path.dirname(output_file)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Ruta del archivo .jsonl de muestras")
    parser.add_argument("--output", required=True, help="Ruta del archivo .jsonl de eventos resumidos")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print("Archivo no encontrado:", args.input)
        return

    print("Procesando eventos desde:", args.input)
    events = build_events(args.input)
    print(f"Eventos detectados: {len(events)}")

    save_events(events, args.output)
    print("Guardado en:", args.output)


if __name__ == "__main__":
    main()
