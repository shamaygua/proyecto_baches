import os
import json
import argparse
from ultralytics import YOLO


def extract_timestamp(filename):
    parts = filename.split("_")
    if len(parts) >= 3:
        return "_".join(parts[2:]).replace(".jpg", "")
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-folder", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--imgsz", type=int, default=640)
    args = parser.parse_args()

    model = YOLO(args.model_path)

    files = sorted([
        f for f in os.listdir(args.input_folder)
        if f.lower().endswith(".jpg")
    ])

    with open(args.output_file, "w", encoding="utf-8") as f_out:
        for filename in files:
            path = os.path.join(args.input_folder, filename)

            results = model(path, imgsz=args.imgsz, verbose=False)
            r = results[0]

            has_detection = False
            max_conf = 0.0
            num_detections = 0
            has_masks = False

            if r.boxes is not None:
                num_detections = len(r.boxes)
                if num_detections > 0:
                    has_detection = True
                    max_conf = float(r.boxes.conf.max().item())

            if r.masks is not None and num_detections > 0:
                has_masks = True

            sample = {
                "frame": filename,
                "timestamp": extract_timestamp(filename),
                "detections": num_detections,
                "has_pothole": has_detection,
                "has_masks": has_masks,
                "max_confidence": max_conf
            }

            f_out.write(json.dumps(sample, ensure_ascii=False) + "\n")
            print(f"{filename} -> detections={num_detections} conf={max_conf:.2f} masks={has_masks}")

    print("\nInferencia terminada:", args.output_file)


if __name__ == "__main__":
    main()
