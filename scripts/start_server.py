from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import uvicorn

from colab_full_control_mcp.common import ensure_directory
from colab_full_control_mcp.server import create_app
from colab_full_control_mcp.settings import Settings


def server_pid_path(settings: Settings) -> Path:
    return ensure_directory(settings.job_root) / "mcp_server.pid"


def server_log_path(settings: Settings) -> Path:
    return ensure_directory(settings.job_root) / "mcp_server.log"


def run_background(settings: Settings) -> int:
    command = [sys.executable, str(Path(__file__).resolve()), "--foreground"]
    log_path = server_log_path(settings)
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    kwargs = {"cwd": str(ROOT), "stdout": log_path.open("ab"), "stderr": subprocess.STDOUT}
    if os.name == "nt":
        kwargs["creationflags"] = creationflags
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **kwargs)
    server_pid_path(settings).write_text(str(process.pid), encoding="utf-8")
    print(f"Started MCP server in background. pid={process.pid} log={log_path}")
    return 0


def run_foreground(settings: Settings) -> int:
    app = create_app(settings)
    server_pid_path(settings).write_text(str(os.getpid()), encoding="utf-8")
    uvicorn.run(app, host=settings.host, port=settings.port)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--foreground", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    if args.background and args.foreground:
        raise SystemExit("Choose either --background or --foreground")
    if args.background:
        return run_background(settings)
    return run_foreground(settings)


if __name__ == "__main__":
    raise SystemExit(main())

