import json
import time
import os
import argparse
from datetime import datetime

from google.cloud import firestore
from google.oauth2 import service_account


ALLOWED_RESULTS = {
    "bache_confirmado_multimodal",
    "bache_probable_con_apoyo_visual",
    "bache_probable_sensorial",
    "bache_probable_visual"
}

RESULT_PRIORITY = {
    "bache_confirmado_multimodal": 4,
    "bache_probable_con_apoyo_visual": 3,
    "bache_probable_sensorial": 2,
    "bache_probable_visual": 1
}


def load_jsonl(path):
    data = []
    if not os.path.exists(path):
        return data

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    data.append(json.loads(line))
                except Exception:
                    pass
    return data


def make_spatial_key(lat, lon, precision=5):
    return f"{round(float(lat), precision)}_{round(float(lon), precision)}"


def safe_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def get_event_timestamp(event):
    return (
        event.get("timestamp")
        or event.get("start_ts")
        or event.get("t_vis")
        or datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    )


def event_is_uploadable(event):
    fusion_result = event.get("fusion_result")

    if fusion_result not in ALLOWED_RESULTS:
        return False, "fusion_result_no_permitido"

    lat = event.get("lat")
    lon = event.get("lon")

    if lat is None or lon is None:
        return False, "sin_gps"

    return True, None


def build_firestore_doc(event, run_id, event_id, dedup_key):
    lat = safe_float(event.get("lat"))
    lon = safe_float(event.get("lon"))

    return {
        "event_id": event_id,
        "run_id": run_id,

        "lat": lat,
        "lon": lon,
        "position": firestore.GeoPoint(lat, lon),

        "timestamp": get_event_timestamp(event),

        "severity": event.get("severity"),
        "severity_mode": event.get("severity_mode"),

        "fusion_result": event.get("fusion_result"),
        "type": "visual_only" if event.get("visual_only") else "sensor_fusion",

        "sensor_event": bool(event.get("sensor_event")),
        "vision_detected": bool(event.get("vision_detected")),
        "visual_only": bool(event.get("visual_only")),
        "is_bache_confirmed": bool(event.get("is_bache_confirmed")),

        "confidence": safe_float(event.get("confidence")),
        "vision_max_confidence": safe_float(event.get("vision_max_confidence")),

        "depth_mm": safe_float(event.get("depth_mm")),
        "depth_source": event.get("depth_source"),
        "tof_sensor_assigned": event.get("tof_sensor_assigned"),
        "tof_match_found": bool(event.get("tof_match_found")),

        "area_px": safe_float(event.get("area_px")),
        "area_cm2": safe_float(event.get("area_cm2")),

        "x_center_norm": safe_float(event.get("x_center_norm")),
        "visual_track_id": event.get("visual_track_id"),
        "frame": event.get("frame"),

        "dedup_key": dedup_key,
        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    }


def choose_best_event_by_spatial_key(events):
    best_by_key = {}

    for event in events:
        uploadable, reason = event_is_uploadable(event)
        if not uploadable:
            continue

        lat = event.get("lat")
        lon = event.get("lon")
        fusion_result = event.get("fusion_result")

        spatial_key = make_spatial_key(lat, lon, precision=5)

        current = best_by_key.get(spatial_key)

        if current is None:
            best_by_key[spatial_key] = event
            continue

        current_priority = RESULT_PRIORITY.get(current.get("fusion_result"), 0)
        new_priority = RESULT_PRIORITY.get(fusion_result, 0)

        if new_priority > current_priority:
            best_by_key[spatial_key] = event
            continue

        if new_priority == current_priority:
            current_conf = current.get("confidence") or current.get("vision_max_confidence") or 0.0
            new_conf = event.get("confidence") or event.get("vision_max_confidence") or 0.0

            current_area = current.get("area_px") or 0
            new_area = event.get("area_px") or 0

            if (new_conf, new_area) > (current_conf, current_area):
                best_by_key[spatial_key] = event

    return best_by_key


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--ssd-root", default="/mnt/ssd/proyecto_baches")
    parser.add_argument("--key-path", required=True)
    parser.add_argument("--collection", default="baches")
    parser.add_argument("--poll-interval", type=float, default=5.0)
    args = parser.parse_args()

    credentials = service_account.Credentials.from_service_account_file(args.key_path)
    db = firestore.Client(credentials=credentials)

    fused_file = os.path.join(
        args.ssd_root,
        "fusion",
        f"run_{args.run_id}",
        "fused_events.jsonl"
    )

    uploaded_doc_ids = set()

    print("[FIREBASE] Iniciado uploader")
    print("[FIREBASE] Archivo:", fused_file)

    while True:
        if not os.path.exists(fused_file):
            print("[FIREBASE] Esperando archivo fusionado...")
            time.sleep(args.poll_interval)
            continue

        events = load_jsonl(fused_file)
        best_by_key = choose_best_event_by_spatial_key(events)

        for spatial_key, event in best_by_key.items():
            fusion_result = event.get("fusion_result")
            dedup_key = f"{spatial_key}"

            doc_id = f"{args.run_id}_{dedup_key}"

            if doc_id in uploaded_doc_ids:
                continue

            uploadable, reason = event_is_uploadable(event)
            if not uploadable:
                continue

            doc = build_firestore_doc(
                event=event,
                run_id=args.run_id,
                event_id=doc_id,
                dedup_key=dedup_key
            )

            try:
                db.collection(args.collection).document(doc_id).set(doc)
                uploaded_doc_ids.add(doc_id)
                print(f"[FIREBASE] Subido: {doc_id} | {fusion_result}")

            except Exception as e:
                print("[ERROR FIREBASE]", e)

        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
