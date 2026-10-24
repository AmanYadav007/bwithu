# BwithU in one container: the free pipeline (SenseVoice + Groq + Edge TTS + LAM), its Cloudflare tunnel and a
# freeze watchdog (start.sh). deploy.sh builds it on a VPS; push.py uploads it to a Hugging Face Space (needs PRO).
# Both stage server/, local-only faces and the built web/dist next to this file first. amd64 or arm64.
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 OPENBLAS_NUM_THREADS=1 \
    BWITHU_TRUST_PROXY=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libopus0 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL -o /usr/local/bin/cloudflared \
       https://github.com/cloudflare/cloudflared/releases/download/2026.9.1/cloudflared-linux-$(dpkg --print-architecture) \
    && chmod +x /usr/local/bin/cloudflared
# Spaces run the container as uid 1000; on a VPS it's just an unprivileged user.
RUN useradd -m -u 1000 user
WORKDIR /app/server
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0
COPY server/requirements.txt server/requirements-dev.txt ./
RUN pip install -r requirements-dev.txt
# Models are baked into the image so a restart doesn't re-download them.
COPY server/scripts/fetch_models.sh scripts/fetch_models.sh
RUN PYTHON=python scripts/fetch_models.sh \
    && MODELSCOPE_CACHE=/app/server python -c "from modelscope import snapshot_download; snapshot_download('iic/SenseVoiceSmall')"
COPY server/ ./
COPY web/dist /app/web/dist
COPY start.sh /app/start.sh
RUN sed 's/host: "127.0.0.1"/host: "0.0.0.0"/' config/bwithu_dev.yaml > config/bwithu_space.yaml \
    && mkdir -p temp logs && chown -R user:user /app
USER user
ENV HOME=/home/user
EXPOSE 8282
CMD ["bash", "/app/start.sh"]
