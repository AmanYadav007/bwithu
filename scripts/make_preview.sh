#!/usr/bin/env bash
# Make a 300x400 setup-screen thumbnail from avatars-src/<name>.jpg.
set -euo pipefail
cd "$(dirname "$0")/.."
name="$1"
ffmpeg -loglevel error -y -i "avatars-src/$name.jpg" \
  -vf "crop=iw*0.75:iw*0.75*4/3:iw*0.125:ih*0.02,scale=300:400:flags=lanczos" -q:v 3 "web/public/avatars/$name.jpg"
echo "web/public/avatars/$name.jpg"
