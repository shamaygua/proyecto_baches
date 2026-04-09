import os
import cv2
import argparse


def frame_difference_score(img1, img2, resize_width=320, resize_height=240):
    img1_small = cv2.resize(img1, (resize_width, resize_height))
    img2_small = cv2.resize(img2, (resize_width, resize_height))

    gray1 = cv2.cvtColor(img1_small, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2_small, cv2.COLOR_BGR2GRAY)

    diff = cv2.absdiff(gray1, gray2)
    score = diff.mean()
    return score


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-folder", required=True, help="Carpeta con frames originales")
    parser.add_argument("--output-folder", required=True, help="Carpeta con frames filtrados")
    parser.add_argument("--threshold", type=float, default=6.0, help="Umbral de diferencia media")
    args = parser.parse_args()

    if not os.path.exists(args.input_folder):
        print("Carpeta no encontrada:", args.input_folder)
        return

    os.makedirs(args.output_folder, exist_ok=True)

    files = sorted([
        f for f in os.listdir(args.input_folder)
        if f.lower().endswith(".jpg")
    ])

    if not files:
        print("No se encontraron imágenes en:", args.input_folder)
        return

    kept = 0
    skipped = 0

    prev_kept_img = None

    for filename in files:
        input_path = os.path.join(args.input_folder, filename)
        img = cv2.imread(input_path)

        if img is None:
            print("No se pudo leer:", input_path)
            continue

        if prev_kept_img is None:
            output_path = os.path.join(args.output_folder, filename)
            cv2.imwrite(output_path, img)
            prev_kept_img = img
            kept += 1
            print(f"KEEP  {filename} | primer frame")
            continue

        score = frame_difference_score(prev_kept_img, img)

        if score >= args.threshold:
            output_path = os.path.join(args.output_folder, filename)
            cv2.imwrite(output_path, img)
            prev_kept_img = img
            kept += 1
            print(f"KEEP  {filename} | diff={score:.2f}")
        else:
            skipped += 1
            print(f"SKIP  {filename} | diff={score:.2f}")

    print("\n===== RESUMEN =====")
    print(f"Frames totales: {len(files)}")
    print(f"Frames guardados: {kept}")
    print(f"Frames omitidos: {skipped}")
    print("===================")


if __name__ == "__main__":
    main()
