#!/usr/bin/env bash
# Builds the fake-microphone WAV files used by the e2e tests (needs ffmpeg + the server venv's edge-tts).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p fixtures && cd fixtures
PY="../../../server/.venv/bin/python"
say() { "$PY" -m edge_tts --voice en-US-GuyNeural --text "$1" --write-media "$2"; }
mono='aresample=48000,aformat=channel_layouts=mono'
silence() { echo "-f lavfi -t $1 -i anullsrc=r=48000:cl=mono"; }
say "Hey there! What's your name, and how is your day going?" q.mp3
say "Can you tell me a long story about a dragon who loves the sea?" q1.mp3
say "Actually, stop. What is two plus two?" q2.mp3
ffmpeg -loglevel error -y $(silence 30) -c:a pcm_s16le silence.wav
ffmpeg -loglevel error -y $(silence 3) -i q.mp3 $(silence 20) \
  -filter_complex "[1:a]$mono[q];[0:a][q][2:a]concat=n=3:v=0:a=1" -c:a pcm_s16le question.wav
ffmpeg -loglevel error -y $(silence 3) -i q1.mp3 $(silence 7) -i q2.mp3 $(silence 25) \
  -filter_complex "[1:a]$mono[a];[3:a]$mono[b];[0:a][a][2:a][b][4:a]concat=n=5:v=0:a=1" -c:a pcm_s16le interrupt.wav
rm -f q.mp3 q1.mp3 q2.mp3
echo "fixtures ready"
