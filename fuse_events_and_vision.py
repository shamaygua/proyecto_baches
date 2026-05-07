import json
import os
import argparse
import sys
from datetime import datetime, timedelta

sys.path.append("/home/sha/proyecto_baches")

from fusion.visual_tof_matcher import match_visual_event_with_tof


VISION_CONF_THRESHOLD = 0.60
MATCH_WINDOW_SEC = 0.25
PIXEL_TO_CM2 = 0.05


def load_jsonl(path):
    data = []
    if not os.path.exists(path):
        return data

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    data.append(json.loads(line))
                except Exception:
                    pass
    return data


def save_jsonl(items, output_file):
    out_dir = os.path.dirname(output_file)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def parse_event_ts(ts_str):
    return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")


def parse_frame_ts(ts_str):
    return datetime.strptime(ts_str, "%Y%m%d_%H%M%S_%f")


def frame_ts_to_event_ts(ts_str):
    dt = parse_frame_ts(ts_str)
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def compute_severity(area_px, depth_mm):
    if depth_mm is not None:
        if depth_mm > 30 or (area_px is not None and area_px > 8000):
            return "alta", "visual_plus_depth"
        elif depth_mm > 15:
            return "media", "visual_plus_depth"
        else:
            return "baja", "visual_plus_depth"

    if area_px is not None and area_px > 7000:
        return "media", "visual_only"

    return "baja", "visual_only"


def flatten_valid_vision_objects(vision):
    valid_objects = []

    for v in vision:
        if not v.get("has_pothole"):
            continue

        if (v.get("max_confidence") or 0.0) < VISION_CONF_THRESHOLD:
            continue

        ts = v.get("timestamp")
        if not ts:
            continue

        try:
            parsed_ts = parse_frame_ts(ts)
            frame_ts = frame_ts_to_event_ts(ts)
        except Exception:
            continue

        objects = v.get("objects", []) or []

        for obj in objects:
            confidence = obj.get("confidence")
            area_px = obj.get("mask_area_px", obj.get("area_px"))
            x_center_norm = obj.get("x_center_norm")
            bbox_width_norm = obj.get("bbox_width_norm")

            if confidence is None:
                confidence = 0.0

            if confidence < VISION_CONF_THRESHOLD:
                continue

            if area_px is None or x_center_norm is None or bbox_width_norm is None:
                continue

            obj_uid = f"{v.get('frame')}_{obj.get('idx', obj.get('track_id', 0))}"

            valid_objects.append({
                "_uid": obj_uid,
                "_matched": False,
                "_parsed_ts": parsed_ts,

                "frame": v.get("frame"),
                "timestamp": ts,
                "frame_ts": frame_ts,

                "visual_track_id": obj.get("track_id", obj.get("idx")),
                "confidence": confidence,
                "x_center_norm": x_center_norm,
                "bbox_width_norm": bbox_width_norm,
                "area_px": area_px,
                "bbox_xyxy": obj.get("bbox_xyxy")
            })

    return valid_objects


def nearest_event_with_gps(events, t_vis_dt):
    best = None
    best_dt = None

    for e in events:
        lat = e.get("lat")
        lon = e.get("lon")
        if lat is None or lon is None:
            continue

        candidates_ts = [
            e.get("start_ts"),
            e.get("end_ts"),
            e.get("timestamp")
        ]

        for ts in candidates_ts:
            if not ts:
                continue
            try:
                e_dt = parse_event_ts(ts)
            except Exception:
                continue

            dt_sec = abs((t_vis_dt - e_dt).total_seconds())

            if best is None or dt_sec < best_dt:
                best = e
                best_dt = dt_sec

    return best, best_dt


def is_near_confirmed_visual(obj, fused_events, time_window_sec=1.5):
    try:
        obj_dt = parse_event_ts(obj["frame_ts"])
    except Exception:
        return False

    for e in fused_events:
        if e.get("fusion_result") != "bache_confirmado_multimodal":
            continue

        t_vis = e.get("t_vis") or e.get("start_ts")
        if not t_vis:
            continue

        try:
            e_dt = parse_event_ts(t_vis)
        except Exception:
            continue

        dt = abs((obj_dt - e_dt).total_seconds())

        if dt <= time_window_sec:
            obj_x = obj.get("x_center_norm")
            event_x = e.get("x_center_norm")

            if obj_x is None or event_x is None:
                return True

            if abs(obj_x - event_x) <= 0.20:
                return True

    return False


def build_sensor_event_fusion(event, visual_objects):
    start_ts = event.get("start_ts")
    end_ts = event.get("end_ts")

    if not start_ts or not end_ts:
        fused = dict(event)
        fused.update({
            "sensor_event": True,
            "vision_detected": False,
            "fusion_result": "evento_sin_tiempo",
            "is_bache_confirmed": False,
            "visual_only": False,
            "severity": "baja",
            "severity_mode": "sensor_only",
            "area_px": None,
            "area_cm2": None,
            "depth_mm": None,
            "depth_source": "none",
            "tof_match_found": False,
            "tof_sensor_assigned": None,
            "t_vis": None,
            "visual_track_id": None,
            "confidence": None,
            "x_center_norm": None,
            "best_visual_match": None
        })
        return fused, None

    try:
        event_start = parse_event_ts(start_ts) - timedelta(seconds=MATCH_WINDOW_SEC)
        event_end = parse_event_ts(end_ts) + timedelta(seconds=MATCH_WINDOW_SEC)
    except Exception:
        return None, None

    candidates = [
        obj for obj in visual_objects
        if event_start <= obj["_parsed_ts"] <= event_end
    ]

    tof_buffer_for_event = [{
        "timestamp": event.get("start_ts"),
        "tof1_filt_mm": None,
        "tof2_filt_mm": None,
        "delta_tof1_mm": event.get("max_delta_tof1_mm"),
        "delta_tof2_mm": event.get("max_delta_tof2_mm"),
        "evento_tof1": event.get("evento_tof1_detected", False),
        "evento_tof2": event.get("evento_tof2_detected", False)
    }]

    fused_visual_matches = []

    for obj in candidates:
        visual_event = {
            "event_id": event.get("event_id"),
            "track_id": obj.get("visual_track_id"),
            "frame_ts": obj.get("frame_ts"),
            "x_center_norm": obj.get("x_center_norm"),
            "bbox_width_norm": obj.get("bbox_width_norm"),
            "area_px": obj.get("area_px"),
            "confidence": obj.get("confidence")
        }

        try:
            match = match_visual_event_with_tof(
                visual_event,
                tof_buffer_for_event
            )
            match["_uid"] = obj["_uid"]
            fused_visual_matches.append(match)
        except Exception:
            pass

    best_visual_match = None

    if fused_visual_matches:
        fused_visual_matches.sort(
            key=lambda x: (
                x.get("tof_match_found", False),
                x.get("depth_mm") or 0,
                x.get("area_px") or 0,
                x.get("confidence") or 0.0
            ),
            reverse=True
        )
        best_visual_match = fused_visual_matches[0]

    if best_visual_match:
        for obj in visual_objects:
            if obj["_uid"] == best_visual_match["_uid"]:
                obj["_matched"] = True
                break

    vision_match_found = best_visual_match is not None
    evaluation_result = event.get("evaluation_result", "descartado")

    if vision_match_found:
        if evaluation_result in {"bache_probable", "bache_probable_fuerte"}:
            fusion_result = "bache_confirmado_multimodal"
            is_bache_confirmed = True
        elif evaluation_result in {"irregularidad_geometrica", "irregularidad_dinamica"}:
            fusion_result = "bache_probable_con_apoyo_visual"
            is_bache_confirmed = False
        else:
            fusion_result = "evento_sensorial_con_apoyo_visual"
            is_bache_confirmed = False
    else:
        if evaluation_result in {"bache_probable", "bache_probable_fuerte"}:
            fusion_result = "bache_probable_sensorial"
        elif evaluation_result in {"irregularidad_geometrica", "irregularidad_dinamica"}:
            fusion_result = "irregularidad_sensorial_sin_apoyo_visual"
        else:
            fusion_result = "evento_descartado"
        is_bache_confirmed = False

    area_px = best_visual_match.get("area_px") if best_visual_match else None
    depth_mm = best_visual_match.get("depth_mm") if best_visual_match else None
    area_cm2 = area_px * PIXEL_TO_CM2 if area_px is not None else None

    severity, severity_mode = compute_severity(area_px, depth_mm)

    fused = dict(event)
    fused.update({
        "vision_conf_threshold": VISION_CONF_THRESHOLD,
        "match_window_sec": MATCH_WINDOW_SEC,

        "sensor_event": True,
        "vision_detected": vision_match_found,
        "vision_match_count": 1 if vision_match_found else 0,
        "vision_max_confidence": best_visual_match.get("confidence") if best_visual_match else None,

        "fusion_result": fusion_result,
        "is_bache_confirmed": is_bache_confirmed,

        "t_vis": best_visual_match.get("t_vis") if best_visual_match else None,
        "visual_track_id": best_visual_match.get("visual_track_id") if best_visual_match else None,
        "confidence": best_visual_match.get("confidence") if best_visual_match else None,
        "x_center_norm": best_visual_match.get("x_center_norm") if best_visual_match else None,

        "area_px": area_px,
        "area_cm2": area_cm2,
        "pixel_to_cm2_factor": PIXEL_TO_CM2,

        "depth_mm": depth_mm,
        "depth_source": best_visual_match.get("depth_source") if best_visual_match else "none",
        "tof_sensor_assigned": best_visual_match.get("tof_sensor_assigned") if best_visual_match else None,
        "tof_match_found": best_visual_match.get("tof_match_found") if best_visual_match else False,

        "visual_only": False,
        "severity": severity,
        "severity_mode": severity_mode,

        "best_visual_match": best_visual_match
    })

    return fused, best_visual_match


def build_visual_only_event(obj, source_event, nearest_dt_sec):
    area_px = obj.get("area_px")
    area_cm2 = area_px * PIXEL_TO_CM2 if area_px is not None else None
    severity, severity_mode = compute_severity(area_px, None)

    lat = source_event.get("lat") if source_event else None
    lon = source_event.get("lon") if source_event else None

    return {
        "event_id": f"visual_{obj['_uid']}",
        "start_ts": obj.get("frame_ts"),
        "end_ts": obj.get("frame_ts"),
        "timestamp": obj.get("frame_ts"),

        "lat": lat,
        "lon": lon,
        "gps_usable": bool(lat is not None and lon is not None),
        "gps_source": "nearest_sensor_event" if source_event else "none",
        "gps_nearest_dt_sec": nearest_dt_sec,

        "sensor_event": False,
        "vision_detected": True,
        "vision_match_count": 1,
        "vision_max_confidence": obj.get("confidence"),

        "fusion_result": "bache_probable_visual",
        "is_bache_confirmed": False,

        "t_vis": obj.get("frame_ts"),
        "visual_track_id": obj.get("visual_track_id"),
        "confidence": obj.get("confidence"),
        "x_center_norm": obj.get("x_center_norm"),
        "bbox_width_norm": obj.get("bbox_width_norm"),
        "bbox_xyxy": obj.get("bbox_xyxy"),
        "frame": obj.get("frame"),

        "area_px": area_px,
        "area_cm2": area_cm2,
        "pixel_to_cm2_factor": PIXEL_TO_CM2,

        "depth_mm": None,
        "depth_source": "none",
        "tof_sensor_assigned": None,
        "tof_match_found": False,

        "visual_only": True,
        "severity": severity,
        "severity_mode": severity_mode
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events-file", required=True)
    parser.add_argument("--vision-file", required=True)
    parser.add_argument("--output-events-file", required=True)
    parser.add_argument("--output-visual-only-file", required=True)
    args = parser.parse_args()

    events = load_jsonl(args.events_file)
    vision = load_jsonl(args.vision_file)

    visual_objects = flatten_valid_vision_objects(vision)

    fused_events = []

    for event in events:
        fused, _ = build_sensor_event_fusion(event, visual_objects)
        if fused is not None:
            fused_events.append(fused)

    visual_only_candidates = []

    for obj in visual_objects:
        if obj.get("_matched"):
            continue

        if is_near_confirmed_visual(obj, fused_events):
            continue

        source_event, nearest_dt_sec = nearest_event_with_gps(
            events,
            obj["_parsed_ts"]
        )

        visual_event = build_visual_only_event(
            obj=obj,
            source_event=source_event,
            nearest_dt_sec=nearest_dt_sec
        )

        visual_only_candidates.append(visual_event)
        fused_events.append(visual_event)

    save_jsonl(fused_events, args.output_events_file)
    save_jsonl(visual_only_candidates, args.output_visual_only_file)

    print("Eventos fusionados totales:", len(fused_events))
    print("Objetos visuales válidos:", len(visual_objects))
    print("Visual-only agregados:", len(visual_only_candidates))
    print("Guardado eventos fusionados en:", args.output_events_file)
    print("Guardado visual-only en:", args.output_visual_only_file)


if __name__ == "__main__":
    main()
