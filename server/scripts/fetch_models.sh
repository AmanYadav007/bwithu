#!/usr/bin/env bash
# Downloads the LAM lip-sync models into server/models (about 750 MB).
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
mkdir -p models/LAM_audio2exp
if [ ! -f models/wav2vec2-base-960h/pytorch_model.bin ]; then
  "$PY" -c "from huggingface_hub import snapshot_download as d; d('facebook/wav2vec2-base-960h', local_dir='models/wav2vec2-base-960h', allow_patterns=['*.json','*.txt','pytorch_model.bin'])"
fi
if [ ! -f models/LAM_audio2exp/pretrained_models/lam_audio2exp_streaming.tar ]; then
  curl -fsSL -o models/LAM_audio2exp/LAM_audio2exp_streaming.tar \
    https://huggingface.co/3DAIGC/LAM_audio2exp/resolve/main/LAM_audio2exp_streaming.tar
  tar -xf models/LAM_audio2exp/LAM_audio2exp_streaming.tar -C models/LAM_audio2exp
  rm models/LAM_audio2exp/LAM_audio2exp_streaming.tar
fi
echo "Models ready."
