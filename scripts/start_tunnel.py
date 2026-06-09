from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from colab_full_control_mcp.common import ensure_directory
from colab_full_control_mcp.settings import Settings


URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)


def tunnel_state_path(settings: Settings) -> Path:
    return ensure_directory(settings.job_root) / "cloudflared_state.json"


def start_tunnel(server_url: str) -> dict[str, str]:
    settings = Settings()
    state_path = tunnel_state_path(settings)
    command = ["cloudflared", "tunnel", "--url", server_url, "--no-autoupdate"]
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    kwargs = {"cwd": str(ROOT), "stdout": subprocess.PIPE, "stderr": subprocess.STDOUT, "text": True}
    if os.name == "nt":
        kwargs["creationflags"] = creationflags
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **kwargs)
    url = None
    deadline = time.time() + 60
    while time.time() < deadline:
        assert process.stdout is not None
        line = process.stdout.readline()
        if not line:
            if process.poll() is not None:
                break
            continue
        match = URL_RE.search(line)
        if match:
            url = match.group(0)
            break
    if url is None:
        process.terminate()
        raise RuntimeError("Failed to capture a trycloudflare URL from cloudflared output")
    state = {"pid": process.pid, "url": url, "server_url": server_url}
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    state = start_tunnel(args.server_url)
    print(json.dumps(state, indent=2))
    print(f"MCP URL: {state['url']}/mcp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

