#!/bin/bash
# nohup bash run.sh --force > whisper.log 2>&1 &
# bash run.sh
# bash run.sh --force # reprocess all recogonized subtitles
# bash run.sh --force "file.name" # reprocess a specific file
# V2T_LANGUAGE=zh bash run.sh --force # force to recognize all files in Chinese
# V2T_LANGUAGE=en bash run.sh --force # force to recognize all files in English
# V2T_LANGUAGE=fr bash run.sh --force # force to recognize all files in French
# watch -n 5 nvidia-smi
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="v2t"
CONTAINER_NAME="v2t"
STARTED_AT=$SECONDS
V2T_LANGUAGE="${V2T_LANGUAGE:-auto}"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

cleanup() {
    status=$?
    trap - EXIT INT TERM
    echo
    echo "[CLEANUP] Removing temporary container and Docker network..."
    docker compose -p "$PROJECT_NAME" down --remove-orphans >/dev/null 2>&1 || true
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
    if [ "$status" -eq 0 ]; then
        echo "[CLEANUP] Complete. Total elapsed: $((SECONDS - STARTED_AT)) seconds."
    else
        echo "[CLEANUP] Complete after failure (exit code $status)."
    fi
    exit "$status"
}
trap cleanup EXIT INT TERM

cd "$SCRIPT_DIR"
echo "============================================================"
echo " Voice to SRT"
echo " Project:   $PROJECT_NAME"
echo " Container: $CONTAINER_NAME"
echo " Folder:    $SCRIPT_DIR"
echo " Language:  $V2T_LANGUAGE"
echo "============================================================"
echo "[START] Preparing GPU transcription container..."

docker compose -p "$PROJECT_NAME" run \
    --rm \
    --no-deps \
    --name "$CONTAINER_NAME" \
    --entrypoint python \
    --env "HOST_UID=$HOST_UID" \
    --env "HOST_GID=$HOST_GID" \
    whisper -u /work/transcribe.py --language "$V2T_LANGUAGE" "$@"
