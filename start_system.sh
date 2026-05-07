#!/bin/bash

echo "===== INICIANDO SISTEMA BACHES ====="

MAC="00:25:00:00:63:57"
RFCOMM_DEV="/dev/rfcomm0"
PROJECT_DIR="/home/sha/proyecto_baches"
VENV_ACTIVATE="$PROJECT_DIR/venv/bin/activate"

RUN_ID="$(date +%Y%m%d_%H%M%S)"
RUN_NAME="auto_run_${RUN_ID}"

SSD_ROOT="/mnt/ssd/proyecto_baches"

LOG_DIR="$SSD_ROOT/logs/run_${RUN_ID}"
VISION_RESULTS_DIR="$SSD_ROOT/vision/results/run_${RUN_ID}"
FUSION_DIR="$SSD_ROOT/fusion/run_${RUN_ID}"
EVAL_DIR="$SSD_ROOT/evaluation/run_${RUN_ID}"

mkdir -p "$LOG_DIR"
mkdir -p "$VISION_RESULTS_DIR"
mkdir -p "$FUSION_DIR"
mkdir -p "$EVAL_DIR"

MAIN_LOG="$LOG_DIR/main.log"
NET_LOG="$LOG_DIR/network_monitor.log"
BAT_LOG="$LOG_DIR/battery_monitor.log"
SAFE_LOG="$LOG_DIR/safe_shutdown.log"
RFCOMM_LOG="$LOG_DIR/rfcomm.log"
CAPTURE_LOG="$LOG_DIR/capture_stream.log"
VISION_LOG="$LOG_DIR/vision_inference.log"
FUSION_LOG="$LOG_DIR/fusion_worker.log"
FIREBASE_LOG="$LOG_DIR/firebase.log"

RUN_ID_FILE="$LOG_DIR/run_id.txt"

NET_PID=""
BAT_PID=""
SAFE_PID=""
CAPTURE_PID=""
VISION_PID=""
FUSION_PID=""
FIREBASE_PID=""

cleanup() {
    echo ""
    echo "===== CERRANDO SISTEMA BACHES ====="

    for pid in "$FIREBASE_PID" "$FUSION_PID" "$VISION_PID" "$CAPTURE_PID" "$SAFE_PID" "$BAT_PID" "$NET_PID"; do
        if [ -n "$pid" ]; then
            kill "$pid" 2>/dev/null
        fi
    done

    sudo rfcomm release 0 2>/dev/null
    echo "===== SISTEMA FINALIZADO ====="
}

trap cleanup EXIT
trap 'exit 0' INT TERM

cd "$PROJECT_DIR" || exit 1

echo "[1] Activando entorno virtual..."
source "$VENV_ACTIVATE" || {
    echo "[ERROR] No se pudo activar el entorno virtual"
    exit 1
}

echo "[2] Reiniciando enlace Bluetooth..."
sudo rfcomm release 0 2>/dev/null
sleep 2

echo "[3] Conectando HC-05..."
sudo rfcomm connect 0 "$MAC" 1 >"$RFCOMM_LOG" 2>&1 &
sleep 4

echo "[4] Verificando creación de $RFCOMM_DEV ..."
INTENTOS=0
MAX_INTENTOS=5

while [ ! -e "$RFCOMM_DEV" ] && [ $INTENTOS -lt $MAX_INTENTOS ]; do
    INTENTOS=$((INTENTOS + 1))
    echo "Intento Bluetooth $INTENTOS/$MAX_INTENTOS ..."
    sudo rfcomm release 0 2>/dev/null
    sleep 2
    sudo rfcomm connect 0 "$MAC" 1 >>"$RFCOMM_LOG" 2>&1 &
    sleep 4
done

if [ ! -e "$RFCOMM_DEV" ]; then
    echo "[ERROR] No se pudo crear $RFCOMM_DEV"
    exit 1
fi

echo "[5] Configurando puerto serial Bluetooth..."
stty -F "$RFCOMM_DEV" 9600 cs8 -cstopb -parenb raw -echo || {
    echo "[ERROR] No se pudo configurar $RFCOMM_DEV"
    exit 1
}

echo "[6] Probando lectura inicial del GPS..."
timeout 5 cat "$RFCOMM_DEV" > /tmp/gps_preview.txt 2>/dev/null

if [ ! -s /tmp/gps_preview.txt ]; then
    echo "[ADVERTENCIA] No se recibió texto inicial del GPS."
    echo "Se continúa; el gps_reader intentará reconectar durante ejecución."
else
    echo "[OK] Se detectó tráfico GPS/Bluetooth:"
    head -n 3 /tmp/gps_preview.txt
fi

echo "[7] Iniciando monitoreo de red..."
python3 "$PROJECT_DIR/automation/network_monitor.py" >"$NET_LOG" 2>&1 &
NET_PID=$!

echo "[8] Iniciando monitoreo de batería..."
python3 "$PROJECT_DIR/automation/battery_monitor.py" >"$BAT_LOG" 2>&1 &
BAT_PID=$!

echo "[9] Iniciando apagado seguro por botón..."
python3 "$PROJECT_DIR/system/safe_shutdown.py" >"$SAFE_LOG" 2>&1 &
SAFE_PID=$!

echo "[10] RUN_ID = $RUN_ID"
echo "$RUN_ID" > "$RUN_ID_FILE"

echo "[11] Iniciando captura de cámara..."
python3 "$PROJECT_DIR/vision/capture_stream.py" \
    --run-id "$RUN_ID" \
    --output-root "$SSD_ROOT/frames" \
    >"$CAPTURE_LOG" 2>&1 &
CAPTURE_PID=$!

sleep 2

echo "[12] Iniciando inferencia continua..."
python3 "$PROJECT_DIR/vision/vision_inference.py" \
    --input-folder "$SSD_ROOT/frames/run_${RUN_ID}" \
    --output-file "$VISION_RESULTS_DIR/vision.jsonl" \
    --registry-file "$VISION_RESULTS_DIR/processed_frames.txt" \
    --model-path "$PROJECT_DIR/models/best.pt" \
    --continuous \
    --poll-interval 1.0 \
    >"$VISION_LOG" 2>&1 &
VISION_PID=$!

sleep 2

echo "[13] Iniciando worker de fusión..."
python3 "$PROJECT_DIR/fusion/fusion_worker.py" \
    --run-id "$RUN_ID" \
    --poll-interval 2.0 \
    >"$FUSION_LOG" 2>&1 &
FUSION_PID=$!

sleep 2

echo "[14] Iniciando uploader Firebase..."
python3 "$PROJECT_DIR/firebase/firestore_uploader.py" \
    --run-id "$RUN_ID" \
    --key-path "$PROJECT_DIR/firebase/serviceAccountKey.json" \
    >"$FIREBASE_LOG" 2>&1 &
FIREBASE_PID=$!

sleep 2

echo "[15] Iniciando pipeline principal..."
python3 "$PROJECT_DIR/main/main_processing.py" \
    --run-name "$RUN_NAME" \
    >"$MAIN_LOG" 2>&1
