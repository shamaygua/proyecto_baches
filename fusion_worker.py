import os
import time
import argparse
import subprocess


def file_exists_and_not_empty(path):
    return os.path.exists(path) and os.path.getsize(path) > 0


def run_command(cmd, step_name):
    print(f"[FUSION_WORKER] Ejecutando: {step_name}")
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.stderr.strip():
            print(result.stderr.strip())
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR][{step_name}] Código de salida: {e.returncode}")
        if e.stdout:
            print(e.stdout)
        if e.stderr:
            print(e.stderr)
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True, help="ID de corrida")
    parser.add_argument(
        "--project-root",
        default="/home/sha/proyecto_baches",
        help="Raíz del proyecto"
    )
    parser.add_argument(
        "--ssd-root",
        default="/mnt/ssd/proyecto_baches",
        help="Raíz de datos en SSD"
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Intervalo entre ciclos"
    )
    parser.add_argument(
        "--idle-exit-seconds",
        type=float,
        default=0.0,
        help="Si > 0, sale tras ese tiempo sin cambios"
    )
    args = parser.parse_args()

    run_name = f"auto_run_{args.run_id}"

    processed_file = os.path.join(args.ssd_root, "processed", f"{run_name}.jsonl")
    vision_file = os.path.join(args.ssd_root, "vision", "results", f"run_{args.run_id}", "vision.jsonl")

    eval_dir = os.path.join(args.ssd_root, "evaluation", f"run_{args.run_id}")
    fusion_dir = os.path.join(args.ssd_root, "fusion", f"run_{args.run_id}")

    os.makedirs(eval_dir, exist_ok=True)
    os.makedirs(fusion_dir, exist_ok=True)

    events_built_file = os.path.join(eval_dir, "events_built.jsonl")
    events_all_file = os.path.join(eval_dir, "events_all.jsonl")
    events_final_file = os.path.join(eval_dir, "events_final.jsonl")

    fused_file = os.path.join(fusion_dir, "fused_events.jsonl")
    visual_only_file = os.path.join(fusion_dir, "visual_only.jsonl")

    event_builder_script = os.path.join(args.project_root, "postprocess", "event_builder.py")
    event_evaluator_script = os.path.join(args.project_root, "evaluation", "event_evaluator.py")
    fuse_script = os.path.join(args.project_root, "fusion", "fuse_events_and_vision.py")

    print("[FUSION_WORKER] Iniciado")
    print("[FUSION_WORKER] run_id:", args.run_id)
    print("[FUSION_WORKER] processed_file:", processed_file)
    print("[FUSION_WORKER] vision_file:", vision_file)

    last_input_signature = None
    last_new_time = time.time()

    try:
        while True:
            processed_ready = file_exists_and_not_empty(processed_file)
            vision_ready = file_exists_and_not_empty(vision_file)

            if not processed_ready:
                print("[FUSION_WORKER] Esperando archivo sensorial...")
                time.sleep(args.poll_interval)
                continue

            if not vision_ready:
                print("[FUSION_WORKER] Esperando archivo de visión...")
                time.sleep(args.poll_interval)
                continue

            current_signature = (
                os.path.getsize(processed_file),
                os.path.getmtime(processed_file),
                os.path.getsize(vision_file),
                os.path.getmtime(vision_file)
            )

            if current_signature != last_input_signature:
                last_input_signature = current_signature
                last_new_time = time.time()

                ok_builder = run_command(
                    [
                        "python3",
                        event_builder_script,
                        "--input", processed_file,
                        "--output", events_built_file
                    ],
                    "event_builder"
                )

                if not ok_builder:
                    time.sleep(args.poll_interval)
                    continue

                ok_evaluator = run_command(
                    [
                        "python3",
                        event_evaluator_script,
                        "--input", events_built_file,
                        "--output-all", events_all_file,
                        "--output-final", events_final_file
                    ],
                    "event_evaluator"
                )

                if not ok_evaluator:
                    time.sleep(args.poll_interval)
                    continue

                ok_fuse = run_command(
                    [
                        "python3",
                        fuse_script,
                        "--events-file", events_final_file,
                        "--vision-file", vision_file,
                        "--output-events-file", fused_file,
                        "--output-visual-only-file", visual_only_file
                    ],
                    "fuse_events_and_vision"
                )

                if ok_fuse:
                    print("[FUSION_WORKER] Fusión actualizada correctamente")

            if args.idle_exit_seconds > 0:
                idle_time = time.time() - last_new_time
                if idle_time >= args.idle_exit_seconds:
                    print(f"[FUSION_WORKER] Sin cambios por {idle_time:.1f}s. Saliendo.")
                    break

            time.sleep(args.poll_interval)

    except KeyboardInterrupt:
        print("\n[FUSION_WORKER] Detenido por usuario")


if __name__ == "__main__":
    main()
