#!/bin/bash

# nohup bash run.sh > whisper.log 2>&1 &

# ================= Configuration =================
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR" || exit 1
# Docker Compose configuration file path
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
CONTAINER_NAME="whisper"   # container_name defined in docker-compose.yml

# Whisper service URL
SERVER_URL="http://localhost:8080/v1/audio/transcriptions"
# SERVER_URL="http://localhost:8080/v1/audio/translations"  # For translation, change transcriptions to translations
# Model name
MODEL="large-v3"

# Source language (set to zh; in translation mode it may be omitted or left as zh)
LANGUAGE="zh"
# LANGUAGE="en"

# Supported audio/video extensions
EXTENSIONS=("mp3" "wav" "m4a" "flac" "aac" "ogg" "mp4" "mkv")

# ================= Chunking configuration =================
# Maximum chunk duration in seconds (1500 seconds = 25 minutes)
MAX_DURATION=960
# Overlap between adjacent chunks in seconds. Subtitles from this portion of the later chunk
# are discarded during merging in favor of the earlier chunk's better-context result.
OVERLAP_DURATION=60
# =========================================

if [ "$OVERLAP_DURATION" -ge "$MAX_DURATION" ]; then
    echo "[ERROR] Overlap duration must be shorter than chunk duration."
    exit 1
fi

CHUNK_STEP=$((MAX_DURATION - OVERLAP_DURATION))

# Check for ffmpeg tools
if ! command -v ffmpeg &> /dev/null || ! command -v ffprobe &> /dev/null; then
    echo "[ERROR] ffmpeg or ffprobe is missing. Install ffmpeg first (for example: sudo apt install ffmpeg)"
    exit 1
fi

# Get the directory containing this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR" || exit 1

# Ensure the standalone subtitle merge script exists
if [ ! -f "temp_merge_chunks.py" ]; then
    echo "[ERROR] Standalone merge script temp_merge_chunks.py was not found!"
    echo "Make sure temp_merge_chunks.py and run.sh are in the same directory."
    exit 1
fi

# Check whether the container is running
if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null)" != "true" ]; then
    echo "[INFO] Container is not running; starting: $CONTAINER_NAME ..."
    docker compose -f "$COMPOSE_FILE" up -d
    
    echo "[WAIT] Container started; waiting 20 seconds for the model to load..."
    sleep 20
else
    echo "[OK] Container $CONTAINER_NAME is already running; no wait is needed."
fi

echo "=========================================="
echo " Scanning directory: $SCRIPT_DIR"
echo " Service URL: $SERVER_URL"
echo "=========================================="

# Enable nullglob so unmatched patterns do not remain literal
shopt -s nullglob nocaseglob

for ext in "${EXTENSIONS[@]}"; do
    for audio_file in *."$ext"; do
        # Ensure this is a regular file
        [ -f "$audio_file" ] || continue

        # Get the base filename and output SRT filename
        filename="${audio_file%.*}"
        srt_file="${filename}.srt"

        # Check whether an SRT with the same name already exists
        if [ -f "$srt_file" ]; then
            echo "[SKIP] Subtitle file already exists: $srt_file"
            continue
        fi

        echo "------------------------------------------"
        echo "[PROCESSING] Inspecting: $audio_file ..."
        
        # 1. Probe the media duration
        duration_float=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$audio_file")
        duration=${duration_float%.*} # Keep the integer portion

        if [ -z "$duration" ]; then
            echo "[WARNING] Could not read the file duration; processing it as a whole..."
            duration=0
        fi

        # 2. Split files longer than 25 minutes
        if [ "$duration" -gt "$MAX_DURATION" ]; then
            echo "[CHUNKING] File is longer than 25 minutes (${duration} seconds); starting chunked processing..."
            temp_dir="temp_chunks_${filename}"
            mkdir -p "$temp_dir"

            # Start a new chunk every 24 minutes, with up to 25 minutes per chunk and a 1-minute overlap.
            # Track every chunk, including failed ones, so later timestamps do not shift forward after a recognition failure.
            chunk_srts=()
            successful_chunks=0
            chunk_index=0
            chunk_start=0
            while [ $((chunk_start + OVERLAP_DURATION)) -lt "$duration" ]; do
                chunk_file=$(printf "%s/chunk_%03d.wav" "$temp_dir" "$chunk_index")
                chunk_name="${chunk_file%.*}"
                chunk_srt="${chunk_name}.srt"
                chunk_srts+=("$chunk_srt")
                rm -f "$chunk_srt"

                echo "  -> Extracting chunk: $chunk_file (starting at ${chunk_start} seconds)..."
                if ! ffmpeg -y -i "$audio_file" -ss "$chunk_start" -t "$MAX_DURATION" \
                  -vn -c:a pcm_s16le -ar 16000 -ac 1 "$chunk_file" -loglevel error; then
                    echo "  [FAILED] Could not extract chunk $chunk_file"
                    chunk_index=$((chunk_index + 1))
                    chunk_start=$((chunk_start + CHUNK_STEP))
                    continue
                fi
                
                echo "  -> Transcribing chunk: $chunk_file ..."
                http_code=$(curl -s -w "%{http_code}" "$SERVER_URL" \
                  -F "file=@$chunk_file" \
                  -F "model=$MODEL" \
                  -F "language=$LANGUAGE" \
                  -F "response_format=srt" \
                  -o "$chunk_srt")

                if [ "$http_code" -eq 200 ] && [ -s "$chunk_srt" ]; then
                    successful_chunks=$((successful_chunks + 1))
                else
                    echo "  [FAILED] Chunk $chunk_file transcription failed (HTTP: $http_code)"
                    rm -f "$chunk_srt"
                fi

                chunk_index=$((chunk_index + 1))
                chunk_start=$((chunk_start + CHUNK_STEP))
            done

            # Merge all chunk SRT files and adjust their timestamps
            if [ "$successful_chunks" -gt 0 ]; then
                echo "  -> Merging subtitle chunks and aligning timestamps..."
                python3 temp_merge_chunks.py "$srt_file" "$MAX_DURATION" "$OVERLAP_DURATION" "${chunk_srts[@]}"
                echo "[SUCCESS] Full subtitle file generated: $srt_file"
            else
                echo "[ERROR] All chunks failed transcription."
            fi

            # Clean up the temporary directory
            rm -rf "$temp_dir"
            
        else
            # Process files no longer than 25 minutes as a whole
            echo "  -> File is short (${duration} seconds); transcribing it as a whole..."
            http_code=$(curl -s -w "%{http_code}" "$SERVER_URL" \
              -F "file=@$audio_file" \
              -F "model=$MODEL" \
              -F "language=$LANGUAGE" \
              -F "response_format=srt" \
              -o "$srt_file")

            if [ "$http_code" -eq 200 ] && [ -s "$srt_file" ]; then
                echo "[SUCCESS] Subtitle file generated: $srt_file"
            else
                echo "[FAILED] Processing $audio_file failed (HTTP status: $http_code)"
                rm -f "$srt_file"
            fi
        fi

        # 3. Run merge_srt.py for final processing
        if [ -f "$srt_file" ]; then
            python3 merge_srt.py "$srt_file"
        fi

    done
done

# docker compose -f "$COMPOSE_FILE" down --rmi all
docker compose -f "$COMPOSE_FILE" down

echo "=========================================="
echo " All audio processing is complete!"
echo "=========================================="
