"""Deploy BwithU to a private Hugging Face Space.

Stages git-tracked server/ files, local-only faces (gitignored real-person files), the built web/dist and this
folder's Dockerfile + start.sh, uploads them, and syncs the Space secrets from the repo's .env.

    cd web && npx vite build && cd ..
    set -a; . ./.env; set +a; server/.venv/bin/python deploy/container/push.py [owner/space]

Hugging Face now requires a PRO subscription for Docker Spaces, even on the free CPU hardware.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SECRETS = ["LLM_API_URL", "LLM_MODEL", "LLM_API_KEY", "BWITHU_ADMIN_TOKEN", "CLOUDFLARE_TUNNEL_TOKEN"]
LOCAL_ONLY = ["server/src/handlers/client/ws_lam_client/lam_samples/varshika.zip"]
CARD = """---
title: BwithU
emoji: 💬
colorFrom: purple
colorTo: blue
sdk: docker
app_port: 8282
pinned: false
---

BwithU call server. Public site: https://app.bwithu.live
"""


def stage(dest: Path) -> None:
    tracked = subprocess.run(["git", "ls-files", "server"], cwd=ROOT, check=True, capture_output=True, text=True)
    for rel in tracked.stdout.splitlines() + LOCAL_ONLY:
        src = ROOT / rel
        if src.is_file():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / rel)
    dist = ROOT / "web" / "dist"
    if not (dist / "index.html").exists():
        sys.exit("web/dist is missing: run `npx vite build` in web/ first")
    shutil.copytree(dist, dest / "web" / "dist")
    for name in ("Dockerfile", "start.sh"):
        shutil.copy2(HERE / name, dest / name)
    (dest / "README.md").write_text(CARD)


def main() -> None:
    api = HfApi(token=os.environ["HF_TOKEN"])
    repo = sys.argv[1] if len(sys.argv) > 1 else f"{api.whoami()['name']}/bwithu"
    api.create_repo(repo, repo_type="space", space_sdk="docker", private=True, exist_ok=True)
    for key in SECRETS:
        if os.environ.get(key):
            api.add_space_secret(repo, key, os.environ[key])
    # The keep-awake ping needs a token that can read this private Space.
    api.add_space_secret(repo, "KEEPALIVE_TOKEN", os.environ["HF_TOKEN"])
    with tempfile.TemporaryDirectory() as tmp:
        stage(Path(tmp))
        api.upload_folder(folder_path=tmp, repo_id=repo, repo_type="space", delete_patterns="*",
                          commit_message="Deploy BwithU")
    print(f"https://huggingface.co/spaces/{repo}")


if __name__ == "__main__":
    main()
