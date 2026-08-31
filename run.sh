#!/bin/bash

# ================= CONFIGURATION =================
# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Docker Compose configuration file
# docker-compose.yml is located in the same directory as this script
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
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
# =================================================

# Change to the script directory
cd "$SCRIPT_DIR" || exit 1

# Check whether the Docker Compose file exists
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "[Error] Docker Compose file not found:"
    echo "$COMPOSE_FILE"
    exit 1
fi

# Check whether merge_srt.py exists
if [ ! -f "$SCRIPT_DIR/merge_srt.py" ]; then
    echo "[Error] merge_srt.py not found:"
    echo "$SCRIPT_DIR/merge_srt.py"
    exit 1
fi

# Check whether the container is running
if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null)" != "true" ]; then
    echo "[Notice] Container is not running. Starting: $CONTAINER_NAME ..."
    docker compose -f "$COMPOSE_FILE" up -d
    echo "[Waiting] Container started. Waiting 20 seconds for the model to load..."
    sleep 20
else
    echo "[OK] Container $CONTAINER_NAME is already running. No need to wait."
fi

echo "=========================================="
echo " Starting to scan folder: $SCRIPT_DIR"
echo " Service URL: $SERVER_URL"
echo "=========================================="

# Enable nullglob to prevent unmatched patterns from being treated as literal strings
shopt -s nullglob nocaseglob

# Process all supported file types
for ext in "${EXTENSIONS[@]}"; do
    for audio_file in *."$ext"; do
    
        # Make sure it is a regular file
        [ -f "$audio_file" ] || continue

        # Get the filename without the extension
        filename="${audio_file%.*}"

        # Define the output SRT filename
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

        # Check HTTP status and whether the SRT file contains data
        if [ "$http_code" -eq 200 ] && [ -s "$srt_file" ]; then
            echo "[Success] Subtitle generated: $srt_file"
            
            # Merge/modify the generated SRT
            python3 "$SCRIPT_DIR/merge_srt.py" "$srt_file"
            
        else
            echo "[Failed] Failed to process $audio_file (HTTP status code: $http_code)"

            # Delete the file if an empty or invalid file was generated
            rm -f "$srt_file"

        fi
    done
done

# Stop Docker Compose and remove images
docker compose -f "$COMPOSE_FILE" down -rmi all

echo "=========================================="
echo " All audio processing completed!"
echo "=========================================="
