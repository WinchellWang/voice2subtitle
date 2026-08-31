# voice2subtitle
An open source Docker image that can be used to convert audio and video files into subtitles.

# Purpose

Automatically recognize the voice in a video or audio file and export it as an SRT file with timestamp.

# Requirement

Nvidia GPU with CUDA, CUDA toolkit, linux system, python, docker

# Comptiable file extension

mp3, wav, m4a, flac, aac, ogg, mp4, mkv

# Guide

1. Pull the repo to local ``git clone https://github.com/WinchellWang/voice2subtitle.git``
2. Copy the video or audio files into the repo folder.
3. Change the language in 'run.sh' on line 17 to match the primary language of the file.
4. Execute ``./run.sh``

You should see two SRT files after the task. '*.srt' and '*_merged.srt'. The latter is the final version.

> Run the program in the background while keeping the log by executing the command ```nohup bash run.sh > whisper.log 2>&1 &```. You should then be able to track the status in the 'whisper.log' file in the same folder.

> Check the GPU usage regularly using the command ```watch -n 5 nvidia-smi```
