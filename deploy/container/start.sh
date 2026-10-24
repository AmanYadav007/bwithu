#!/usr/bin/env bash
# Hugging Face Space entrypoint: BwithU server under a freeze watchdog, the Cloudflare tunnel that serves
# app.bwithu.live, and a keep-awake ping.
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

# Free Spaces sleep after 48 h without requests through *.hf.space, and visitors come in through the tunnel
# instead, so ping our own Space URL every 6 hours. A private Space needs a token for that.
if [ -n "${SPACE_HOST:-}" ] && [ -n "${KEEPALIVE_TOKEN:-}" ]; then
  (while true; do
    sleep 21600
    curl -s -o /dev/null -m 30 -H "Authorization: Bearer $KEEPALIVE_TOKEN" "https://$SPACE_HOST/openavatarchat/initconfig"
  done) &
fi

while true; do
  python src/demo.py --config config/bwithu_space.yaml &
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
