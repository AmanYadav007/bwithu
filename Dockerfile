# BwithU: one CPU container serving the web app and the call server on :8282.
# Build from the repo root:  docker build -t bwithu .

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npx vite build

FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libopus0 curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app/server
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0
COPY server/requirements.txt ./
RUN pip install -r requirements.txt
COPY server/scripts/fetch_models.sh scripts/fetch_models.sh
RUN PYTHON=python scripts/fetch_models.sh
COPY server/ ./
COPY --from=web /web/dist /app/web/dist
EXPOSE 8282
HEALTHCHECK --interval=30s --timeout=5s CMD curl -fs http://127.0.0.1:8282/openavatarchat/initconfig || exit 1
CMD ["python", "src/demo.py", "--config", "config/bwithu.yaml"]
