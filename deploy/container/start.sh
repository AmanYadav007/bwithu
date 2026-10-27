#!/usr/bin/env bash
# Container entrypoint: BwithU server under a freeze watchdog, and the Cloudflare tunnel that serves
# app.bwithu.live.
set -u
cd /app/server
HEALTH=http://127.0.0.1:8282/openavatarchat/initconfig

if [ -n "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]; then
  (while true; do
    cloudflared tunnel --no-autoupdate run --token "$CLOUDFLARE_TUNNEL_TOKEN"
    echo "start.sh: cloudflared exited; restarting in 5s"
    sleep 5
  done) &
fi

while true; do
  python src/demo.py --config config/bwithu_container.yaml &
  pid=$!
  # Startup loads the models; give it up to 5 minutes.
  for _ in $(seq 1 150); do
    curl -fs -o /dev/null -m 5 "$HEALTH" && break
    kill -0 "$pid" 2>/dev/null || break
    sleep 2
  done
  fails=0
  while kill -0 "$pid" 2>/dev/null; do
    sleep 20
    if curl -fs -o /dev/null -m 10 "$HEALTH"; then fails=0; else fails=$((fails + 1)); fi
    if [ "$fails" -ge 3 ]; then
      echo "start.sh: server not answering for a minute; dumping stacks and restarting"
      kill -USR1 "$pid"
      sleep 2
      kill -9 "$pid"
      break
    fi
  done
  wait "$pid" 2>/dev/null
  echo "start.sh: server exited; restarting in 3s"
  sleep 3
done
