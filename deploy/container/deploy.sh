#!/usr/bin/env bash
# Deploy BwithU to a VPS over SSH: build the web app, stage server/ (git-tracked files plus local-only faces),
# copy it with a trimmed .env, then `docker compose up`. The server needs Docker and rsync.
# Usage: deploy/container/deploy.sh ubuntu@92.4.95.48 [ssh-key]
set -euo pipefail
host="$1"
key="${2:-$HOME/.ssh/bwithu_server}"
root="$(cd "$(dirname "$0")/../.." && pwd)"
here="$root/deploy/container"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

(cd "$root/web" && npx vite build > /dev/null)
{
  git -C "$root" ls-files server
  # Real-person files kept out of git (see .gitignore).
  echo "server/src/handlers/client/ws_lam_client/lam_samples/varshika.zip"
} | while IFS= read -r f; do [ -f "$root/$f" ] && echo "$f"; done > "$stage/.files"
rsync -a --files-from="$stage/.files" "$root/" "$stage/"
rm "$stage/.files"
mkdir -p "$stage/web"
cp -R "$root/web/dist" "$stage/web/dist"
cp "$here/Dockerfile" "$here/start.sh" "$here/compose.yml" "$stage/"
# Only what the server needs; other keys in the local .env stay on this machine.
grep -E '^(LLM_API_URL|LLM_MODEL|LLM_API_KEY|BWITHU_ADMIN_TOKEN|CLOUDFLARE_TUNNEL_TOKEN)=' "$root/.env" > "$stage/.env"
chmod 600 "$stage/.env"

ssh_cmd="ssh -i $key"
rsync -az --delete -e "$ssh_cmd" "$stage/" "$host:bwithu/"
$ssh_cmd "$host" 'cd bwithu && docker compose up -d --build && docker compose ps'
