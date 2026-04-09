import json
import os
import argparse

# =========================
# UMBRALES PRELIMINARES DE EVALUACIÓN
# =========================
MIN_DURATION_MS = 120
MIN_AZ_G = 0.015
MIN_DELTA_TOF_MM = 15

STRONG_AZ_G = 0.025
STRONG_DELTA_TOF_MM = 20


def evaluate_event(event):
    duration_ms = event.get("duration_ms", 0) or 0
    max_abs_az = event.get("max_abs_az_filt_g", 0.0) or 0.0
    max_dtof1 = event.get("max_delta_tof1_mm", 0.0) or 0.0
    max_dtof2 = event.get("max_delta_tof2_mm", 0.0) or 0.0

    evento_tof1 = event.get("evento_tof1_detected", False)
    evento_tof2 = event.get("evento_tof2_detected", False)
    evento_tof_ambos = event.get("evento_tof_ambos_detected", False)
    evento_imu_vertical = event.get("evento_imu_vertical_detected", False)
    evento_gyro_apoyo = event.get("evento_gyro_apoyo_detected", False)

    max_delta_tof = max(max_dtof1, max_dtof2)

    rejection_reason = None
    is_valid_event = True

    # =========================
    # DESCARTE
    # =========================
    if duration_ms < MIN_DURATION_MS:
        is_valid_event = False
        rejection_reason = "evento_demasiado_corto"

    if not evento_tof1 and not evento_tof2 and not evento_imu_vertical:
        is_valid_event = False
        rejection_reason = "sin_evidencia_suficiente"

    # =========================
    # CLASIFICACIÓN
    # =========================
    evaluation_result = "descartado"
    is_bache_probable = False
    is_bache_confirmed = False  # reservado para visión futura

    if is_valid_event:
        if max_delta_tof >= STRONG_DELTA_TOF_MM and max_abs_az >= STRONG_AZ_G:
            evaluation_result = "bache_probable_fuerte"
            is_bache_probable = True

        elif max_delta_tof >= MIN_DELTA_TOF_MM and max_abs_az >= MIN_AZ_G:
            evaluation_result = "bache_probable"
            is_bache_probable = True

        elif max_delta_tof >= MIN_DELTA_TOF_MM:
            evaluation_result = "irregularidad_geometrica"

        elif max_abs_az >= MIN_AZ_G and evento_imu_vertical:
            evaluation_result = "irregularidad_dinamica"

        else:
            evaluation_result = "evento_no_concluyente"

    evaluated = dict(event)
    evaluated.update({
        "is_valid_event": is_valid_event,
        "rejection_reason": rejection_reason,
        "max_delta_tof_mm": max_delta_tof,
        "evaluation_result": evaluation_result,
        "is_bache_probable": is_bache_probable,
        "is_bache_confirmed": is_bache_confirmed,

        # reservado para visión
        "vision_available": False,
        "vision_result": None,
        "vision_confidence": None
    })

    return evaluated


def load_events(input_file):
    events = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
    return events


def save_jsonl(events, output_file):
    out_dir = os.path.dirname(output_file)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


def summarize_events(evaluated_events):
    summary = {
        "total_events": len(evaluated_events),
        "valid_events": 0,
        "discarded_events": 0,
        "evento_no_concluyente": 0,
        "irregularidad_geometrica": 0,
        "irregularidad_dinamica": 0,
        "bache_probable": 0,
        "bache_probable_fuerte": 0
    }

    for e in evaluated_events:
        if e.get("is_valid_event"):
            summary["valid_events"] += 1
        else:
            summary["discarded_events"] += 1

        result = e.get("evaluation_result", "descartado")
        if result in summary:
            summary[result] += 1

    return summary


def print_summary(summary):
    print("\n===== RESUMEN DE EVALUACIÓN =====")
    print(f"Eventos evaluados: {summary['total_events']}")
    print(f"Eventos válidos: {summary['valid_events']}")
    print(f"Eventos descartados: {summary['discarded_events']}")
    print(f"Evento no concluyente: {summary['evento_no_concluyente']}")
    print(f"Irregularidad geométrica: {summary['irregularidad_geometrica']}")
    print(f"Irregularidad dinámica: {summary['irregularidad_dinamica']}")
    print(f"Bache probable: {summary['bache_probable']}")
    print(f"Bache probable fuerte: {summary['bache_probable_fuerte']}")
    print("=================================\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Archivo de eventos resumidos")
    parser.add_argument("--output-all", required=True, help="Archivo de salida con todos los eventos evaluados")
    parser.add_argument("--output-final", required=True, help="Archivo de salida con solo eventos válidos")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print("Archivo no encontrado:", args.input)
        return

    input_events = load_events(args.input)
    evaluated_events = [evaluate_event(e) for e in input_events]

    # guardar todos
    save_jsonl(evaluated_events, args.output_all)

    # guardar solo válidos/útiles
    final_events = [
        e for e in evaluated_events
        if e.get("evaluation_result") in {
            "irregularidad_geometrica",
            "irregularidad_dinamica",
            "bache_probable",
            "bache_probable_fuerte"
        }
    ]
    save_jsonl(final_events, args.output_final)

    summary = summarize_events(evaluated_events)
    print_summary(summary)

    print("Archivo evaluado completo:", args.output_all)
    print("Archivo final filtrado:", args.output_final)


if __name__ == "__main__":
    main()
