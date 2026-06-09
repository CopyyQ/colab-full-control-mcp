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


def tunnel_log_path(settings: Settings) -> Path:
    return ensure_directory(settings.job_root) / "cloudflared.log"


def extract_tunnel_url(text: str) -> str | None:
    match = URL_RE.search(text)
    return match.group(0) if match else None


def start_tunnel(server_url: str) -> dict[str, str]:
    settings = Settings()
    state_path = tunnel_state_path(settings)
    log_path = tunnel_log_path(settings)
    command = ["cloudflared", "tunnel", "--url", server_url, "--no-autoupdate"]
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    log_path.write_text("", encoding="utf-8")
    log_handle = log_path.open("ab")
    kwargs = {"cwd": str(ROOT), "stdout": log_handle, "stderr": subprocess.STDOUT}
    if os.name == "nt":
        kwargs["creationflags"] = creationflags
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **kwargs)
    log_handle.close()

    url = None
    deadline = time.time() + 60
    while time.time() < deadline:
        if log_path.exists():
            content = log_path.read_text(encoding="utf-8", errors="replace")
            url = extract_tunnel_url(content)
            if url:
                break
        if process.poll() is not None:
            break
        time.sleep(0.5)
    if url is None:
        process.terminate()
        log_tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:] if log_path.exists() else ""
        raise RuntimeError(f"Failed to capture a trycloudflare URL from cloudflared output. Log tail:\n{log_tail}")
    state = {"pid": process.pid, "url": url, "server_url": server_url, "log_path": str(log_path)}
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
