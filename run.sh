#!/bin/bash

# ================= CONFIGURATION =================
# Docker Compose configuration file path
COMPOSE_FILE="/path/to/folder/docker-compose.yml"
CONTAINER_NAME="whisper"   # container_name defined in docker-compose.yml

# Whisper service URL
SERVER_URL="http://localhost:8080/v1/audio/transcriptions"
# SERVER_URL="http://localhost:8080/v1/audio/translations"  # For translation, change transcriptions to translations

# Model to use
MODEL="large-v3"

# Source language of the audio (set to zh; can be omitted or kept as zh in translation mode)
# LANGUAGE="zh"
LANGUAGE="en"

# Supported audio/video file extensions
EXTENSIONS=("mp3" "wav" "m4a" "flac" "aac" "ogg" "mp4" "mkv")
# ================================================

# Check whether the container is running
if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null)" != "true" ]; then
    echo "[Notice] Container is not running. Starting: $CONTAINER_NAME ..."
    docker compose -f "$COMPOSE_FILE" start
    
    echo "[Waiting] Container started. Waiting 20 seconds for the model to load..."
    sleep 20
else
    echo "[OK] Container $CONTAINER_NAME is already running. No need to wait."
fi

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR" || exit 1

echo "=========================================="
echo " Starting to scan folder: $SCRIPT_DIR"
echo " Service URL: $SERVER_URL"
echo "=========================================="

# Enable nullglob to prevent unmatched patterns from being treated as literal strings
shopt -s nullglob nocaseglob

for ext in "${EXTENSIONS[@]}"; do
    for audio_file in *."$ext"; do
        # Make sure it is a regular file
        [ -f "$audio_file" ] || continue

        # Get the filename without the extension and define the output SRT filename
        filename="${audio_file%.*}"
        srt_file="${filename}.srt"

        # Check whether an SRT file with the same name already exists
        if [ -f "$srt_file" ]; then
            echo "[Skipped] Subtitle file already exists: $srt_file"
            continue
        fi

        echo "------------------------------------------"
        echo "[Processing] Transcribing: $audio_file ..."
        
        # Send the request and save the result as an SRT file
        http_code=$(curl -s -w "%{http_code}" "$SERVER_URL" \
          -F "file=@$audio_file" \
          -F "model=$MODEL" \
          -F "language=$LANGUAGE" \
          -F "response_format=srt" \
          -o "$srt_file")

        if [ "$http_code" -eq 200 ] && [ -s "$srt_file" ]; then
            echo "[Success] Subtitle generated: $srt_file"
        else
            echo "[Failed] Failed to process $audio_file (HTTP status code: $http_code)"
            # Delete the file if an empty or invalid file was generated
            rm -f "$srt_file"
        fi

        python3 merge_srt.py "$srt_file"

    done
done

docker compose -f $COMPOSE_FILE -rmi all

echo "=========================================="
echo " All audio processing completed!"
echo "=========================================="
