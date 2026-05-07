from datetime import datetime

MATCH_WINDOW_MS = 250

TOF1_ZONE = (0.10, 0.35)
TOF2_ZONE = (0.65, 0.90)


def parse_ts(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")


def ms_diff(ts1: str, ts2: str) -> float:
    return abs((parse_ts(ts1) - parse_ts(ts2)).total_seconds() * 1000.0)


def assign_sensor_by_x(x_center_norm: float) -> str | None:
    if TOF1_ZONE[0] <= x_center_norm <= TOF1_ZONE[1]:
        return "tof1"
    if TOF2_ZONE[0] <= x_center_norm <= TOF2_ZONE[1]:
        return "tof2"
    return None


def find_best_tof_match(t_vis: str, sensor_name: str, tof_buffer: list[dict]) -> dict | None:
    candidates = []

    for sample in tof_buffer:
        dt_ms = ms_diff(t_vis, sample["timestamp"])
        if dt_ms > MATCH_WINDOW_MS:
            continue

        if sensor_name == "tof1" and sample.get("evento_tof1"):
            candidates.append({
                "tof_sensor_assigned": "tof1",
                "tof_match_found": True,
                "depth_mm": sample.get("delta_tof1_mm"),
                "depth_source": "direct_tof",
                "tof_sample_ts": sample["timestamp"],
                "tof_dt_ms": dt_ms
            })

        elif sensor_name == "tof2" and sample.get("evento_tof2"):
            candidates.append({
                "tof_sensor_assigned": "tof2",
                "tof_match_found": True,
                "depth_mm": sample.get("delta_tof2_mm"),
                "depth_source": "direct_tof",
                "tof_sample_ts": sample["timestamp"],
                "tof_dt_ms": dt_ms
            })

    if not candidates:
        return None

    # prioriza menor desfase temporal
    candidates.sort(key=lambda x: x["tof_dt_ms"])
    return candidates[0]


def match_visual_event_with_tof(visual_event: dict, tof_buffer: list[dict]) -> dict:
    """
    visual_event esperado:
    {
        "event_id": int,
        "track_id": int,
        "frame_ts": str,
        "x_center_norm": float,
        "bbox_width_norm": float,
        "area_px": float,
        "confidence": float
    }
    """
    x_center = visual_event["x_center_norm"]
    t_vis = visual_event["frame_ts"]

    assigned_sensor = assign_sensor_by_x(x_center)

    result = {
        "event_id": visual_event["event_id"],
        "visual_track_id": visual_event["track_id"],
        "t_vis": t_vis,
        "x_center_norm": visual_event["x_center_norm"],
        "bbox_width_norm": visual_event["bbox_width_norm"],
        "area_px": visual_event["area_px"],
        "confidence": visual_event["confidence"],
        "tof_sensor_assigned": assigned_sensor,
        "tof_match_found": False,
        "depth_mm": None,
        "depth_source": "none",
        "visual_only": True,
        "severity_mode": "visual_only"
    }

    if assigned_sensor is None:
        return result

    tof_match = find_best_tof_match(t_vis, assigned_sensor, tof_buffer)

    if tof_match is not None:
        result.update(tof_match)
        result["visual_only"] = False
        result["severity_mode"] = "visual_plus_depth"

    return result
