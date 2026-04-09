import json
import os
import argparse
from datetime import datetime, timedelta


VISION_CONF_THRESHOLD = 0.60
MATCH_WINDOW_SEC = 2.0


def load_jsonl(path):
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def parse_event_ts(ts_str):
    # formato: "2026-04-05 22:24:49.123"
    return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")


def parse_frame_ts(ts_str):
    # formato desde nombre: "20260405_224657_364"
    return datetime.strptime(ts_str, "%Y%m%d_%H%M%S_%f")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events-file", required=True, help="Archivo de eventos finales")
    parser.add_argument("--vision-file", required=True, help="Archivo de resultados de visión")
    parser.add_argument("--output-events-file", required=True, help="Salida de eventos fusionados")
    parser.add_argument("--output-visual-only-file", required=True, help="Salida de candidatos visuales aislados")
    args = parser.parse_args()

    if not os.path.exists(args.events_file):
        print("No existe:", args.events_file)
        return

    if not os.path.exists(args.vision_file):
        print("No existe:", args.vision_file)
        return

    events = load_jsonl(args.events_file)
    vision = load_jsonl(args.vision_file)

    # Filtrar solo frames visuales válidos
    valid_vision = []
    for v in vision:
        if v.get("has_pothole") and (v.get("max_confidence", 0.0) >= VISION_CONF_THRESHOLD):
            ts = v.get("timestamp")
            if ts:
                try:
                    v["_parsed_ts"] = parse_frame_ts(ts)
                    v["_matched"] = False
                    valid_vision.append(v)
                except Exception:
                    pass

    fused_events = []

    for event in events:
        start_ts = event.get("start_ts")
        end_ts = event.get("end_ts")

        if not start_ts or not end_ts:
            fused = dict(event)
            fused.update({
                "fusion_result": "evento_sin_tiempo",
                "vision_match_found": False,
                "vision_match_count": 0,
                "vision_max_confidence_match": 0.0,
                "is_bache_confirmed": False
            })
            fused_events.append(fused)
            continue

        event_start = parse_event_ts(start_ts) - timedelta(seconds=MATCH_WINDOW_SEC)
        event_end = parse_event_ts(end_ts) + timedelta(seconds=MATCH_WINDOW_SEC)

        matched_frames = [
            v for v in valid_vision
            if event_start <= v["_parsed_ts"] <= event_end
        ]

        for v in matched_frames:
            v["_matched"] = True

        vision_match_found = len(matched_frames) > 0
        vision_match_count = len(matched_frames)
        vision_max_confidence_match = max(
            [v.get("max_confidence", 0.0) for v in matched_frames],
            default=0.0
        )

        evaluation_result = event.get("evaluation_result", "descartado")
        is_bache_confirmed = False

        if vision_match_found:
            if evaluation_result in {"bache_probable", "bache_probable_fuerte"}:
                fusion_result = "bache_confirmado_multimodal"
                is_bache_confirmed = True
            elif evaluation_result in {"irregularidad_geometrica", "irregularidad_dinamica"}:
                fusion_result = "bache_probable_con_apoyo_visual"
            else:
                fusion_result = "evento_sensorial_con_apoyo_visual"
        else:
            if evaluation_result in {"bache_probable", "bache_probable_fuerte"}:
                fusion_result = "bache_probable_sensorial"
            elif evaluation_result in {"irregularidad_geometrica", "irregularidad_dinamica"}:
                fusion_result = "irregularidad_sensorial_sin_apoyo_visual"
            else:
                fusion_result = "evento_descartado"

        fused = dict(event)
        fused.update({
            "vision_conf_threshold": VISION_CONF_THRESHOLD,
            "match_window_sec": MATCH_WINDOW_SEC,
            "vision_match_found": vision_match_found,
            "vision_match_count": vision_match_count,
            "vision_max_confidence_match": vision_max_confidence_match,
            "fusion_result": fusion_result,
            "is_bache_confirmed": is_bache_confirmed
        })

        fused_events.append(fused)

    # Visual-only candidates: válidos que no hicieron match con ningún evento
    visual_only_candidates = []
    for v in valid_vision:
        if not v["_matched"]:
            visual_only_candidates.append({
                "frame": v.get("frame"),
                "timestamp": v.get("timestamp"),
                "detections": v.get("detections"),
                "has_pothole": v.get("has_pothole"),
                "has_masks": v.get("has_masks"),
                "max_confidence": v.get("max_confidence"),
                "vision_conf_threshold": VISION_CONF_THRESHOLD,
                "fusion_result": "bache_probable_visual"
            })

    # Guardar eventos fusionados
    out_dir_1 = os.path.dirname(args.output_events_file)
    if out_dir_1:
        os.makedirs(out_dir_1, exist_ok=True)

    with open(args.output_events_file, "w", encoding="utf-8") as f:
        for item in fused_events:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # Guardar visual-only
    out_dir_2 = os.path.dirname(args.output_visual_only_file)
    if out_dir_2:
        os.makedirs(out_dir_2, exist_ok=True)

    with open(args.output_visual_only_file, "w", encoding="utf-8") as f:
        for item in visual_only_candidates:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print("Eventos sensoriales fusionados:", len(fused_events))
    print("Frames visuales válidos:", len(valid_vision))
    print("Candidatos visuales aislados:", len(visual_only_candidates))
    print("Guardado eventos fusionados en:", args.output_events_file)
    print("Guardado visual-only en:", args.output_visual_only_file)


if __name__ == "__main__":
    main()
