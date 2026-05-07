import os
import json
import time
import argparse
from typing import Optional, Set

import cv2
from ultralytics import YOLO


MIN_AREA_PX = 1200
FRAME_DIFF_THRESHOLD = 6.0


def extract_timestamp(filename: str) -> Optional[str]:
    """
    Espera:
    frame_0001_20260405_222421_480.jpg
    Devuelve:
    20260405_222421_480
    """
    name = os.path.basename(filename)
    parts = name.split("_")
    if len(parts) >= 4:
        return "_".join(parts[2:]).replace(".jpg", "")
    return None


def load_processed_set(registry_file: Optional[str]) -> Set[str]:
    if not registry_file or not os.path.exists(registry_file):
        return set()

    with open(registry_file, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def append_processed(registry_file: Optional[str], filename: str):
    if not registry_file:
        return

    os.makedirs(os.path.dirname(registry_file), exist_ok=True)
    with open(registry_file, "a", encoding="utf-8") as f:
        f.write(filename + "\n")


def append_jsonl(output_file: str, item: dict):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def frame_difference_score(img1, img2) -> float:
    img1_small = cv2.resize(img1, (160, 120))
    img2_small = cv2.resize(img2, (160, 120))

    gray1 = cv2.cvtColor(img1_small, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2_small, cv2.COLOR_BGR2GRAY)

    diff = cv2.absdiff(gray1, gray2)
    return float(diff.mean())


def mask_area_from_result(result, idx: int) -> Optional[int]:
    try:
        if result.masks is None:
            return None
        mask_tensor = result.masks.data[idx]
        return int((mask_tensor > 0).sum().item())
    except Exception:
        return None


def bbox_from_result(result, idx: int):
    try:
        box = result.boxes.xyxy[idx].tolist()
        return [float(x) for x in box]
    except Exception:
        return None


def normalized_geometry_from_bbox(bbox, image_width: int):
    if bbox is None or image_width <= 0:
        return None, None

    x1, y1, x2, y2 = bbox
    x_center = (x1 + x2) / 2.0
    bbox_width = max(0.0, x2 - x1)

    return x_center / image_width, bbox_width / image_width


def process_frame(model, image_path: str, imgsz: int, conf_thres: float) -> dict:
    filename = os.path.basename(image_path)
    timestamp = extract_timestamp(filename)

    result = model.predict(
        source=image_path,
        imgsz=imgsz,
        conf=conf_thres,
        verbose=False
    )[0]

    image_shape = result.orig_shape
    image_height = int(image_shape[0])
    image_width = int(image_shape[1])

    objects = []
    max_confidence = 0.0
    has_masks = result.masks is not None

    if result.boxes is not None and len(result.boxes) > 0:
        for idx in range(len(result.boxes)):
            try:
                confidence = float(result.boxes.conf[idx].item())
            except Exception:
                confidence = 0.0

            bbox = bbox_from_result(result, idx)
            x_center_norm, bbox_width_norm = normalized_geometry_from_bbox(
                bbox,
                image_width
            )

            area_px = mask_area_from_result(result, idx)

            if area_px is not None and area_px < MIN_AREA_PX:
                continue

            max_confidence = max(max_confidence, confidence)

            objects.append({
                "idx": idx,
                "track_id": idx,
                "confidence": confidence,
                "bbox_xyxy": bbox,
                "x_center_norm": x_center_norm,
                "bbox_width_norm": bbox_width_norm,
                "mask_area_px": area_px,
                "area_px": area_px
            })

    return {
        "frame": filename,
        "timestamp": timestamp,
        "image_width": image_width,
        "image_height": image_height,
        "has_pothole": len(objects) > 0,
        "has_masks": has_masks,
        "max_confidence": max_confidence,
        "objects": objects
    }


def resolve_paths(args):
    if args.run_id:
        input_folder = os.path.join(args.frames_root, f"run_{args.run_id}")
        output_dir = os.path.join(args.results_root, f"run_{args.run_id}")
        output_file = os.path.join(output_dir, "vision.jsonl")
        registry_file = os.path.join(output_dir, "processed_frames.txt")
        os.makedirs(output_dir, exist_ok=True)
        return input_folder, output_file, registry_file

    if not args.input_folder or not args.output_file:
        raise ValueError("Debes pasar --run-id o --input-folder y --output-file")

    return args.input_folder, args.output_file, args.registry_file


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--run-id", default=None)
    parser.add_argument("--frames-root", default="/mnt/ssd/proyecto_baches/frames")
    parser.add_argument("--results-root", default="/mnt/ssd/proyecto_baches/vision/results")

    parser.add_argument("--input-folder", default=None)
    parser.add_argument("--output-file", default=None)
    parser.add_argument("--registry-file", default=None)

    parser.add_argument("--model-path", required=True)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf-thres", type=float, default=0.25)

    parser.add_argument("--continuous", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--idle-exit-seconds", type=float, default=0.0)

    parser.add_argument("--deduplicate-frames", action="store_true", default=True)
    parser.add_argument("--frame-diff-threshold", type=float, default=FRAME_DIFF_THRESHOLD)

    args = parser.parse_args()

    input_folder, output_file, registry_file = resolve_paths(args)

    if not os.path.exists(input_folder):
        print("[ERROR][VISION] No existe carpeta de entrada:", input_folder)
        return

    model = YOLO(args.model_path)
    processed_set = load_processed_set(registry_file)

    print("[VISION] Carpeta entrada:", input_folder)
    print("[VISION] Archivo salida:", output_file)
    print("[VISION] Registry:", registry_file)

    prev_kept_img = None
    last_new_time = time.time()

    while True:
        files = sorted([
            f for f in os.listdir(input_folder)
            if f.lower().endswith(".jpg")
        ])

        new_files = [f for f in files if f not in processed_set]

        if not new_files:
            if not args.continuous:
                break

            if args.idle_exit_seconds > 0:
                if time.time() - last_new_time >= args.idle_exit_seconds:
                    break

            time.sleep(args.poll_interval)
            continue

        last_new_time = time.time()

        for filename in new_files:
            image_path = os.path.join(input_folder, filename)
            img = cv2.imread(image_path)

            if img is None:
                print("[VISION][WARN] No se pudo leer:", image_path)
                processed_set.add(filename)
                append_processed(registry_file, filename)
                continue

            if args.deduplicate_frames and prev_kept_img is not None:
                diff_score = frame_difference_score(prev_kept_img, img)
                if diff_score < args.frame_diff_threshold:
                    print(f"[VISION] SKIP duplicado visual: {filename} | diff={diff_score:.2f}")
                    processed_set.add(filename)
                    append_processed(registry_file, filename)
                    continue

            try:
                item = process_frame(
                    model=model,
                    image_path=image_path,
                    imgsz=args.imgsz,
                    conf_thres=args.conf_thres
                )

                append_jsonl(output_file, item)
                prev_kept_img = img

                print(
                    f"[VISION] OK {filename} | "
                    f"has_pothole={item['has_pothole']} | "
                    f"objects={len(item['objects'])} | "
                    f"conf={item['max_confidence']:.2f}"
                )

            except Exception as e:
                print(f"[ERROR][VISION] Fallo procesando {filename}: {e}")

            processed_set.add(filename)
            append_processed(registry_file, filename)

        if not args.continuous:
            break

        time.sleep(args.poll_interval)

    print("[VISION] Finalizado:", output_file)


if __name__ == "__main__":
    main()
