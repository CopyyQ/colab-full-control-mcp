from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.start_tunnel import extract_tunnel_url


def test_stop_tunnel_is_idempotent_for_stale_pid(tmp_path: Path):
    content_root = tmp_path / "content"
    drive_root = content_root / "drive" / "MyDrive"
    job_root = content_root / ".colab_full_control_mcp" / "jobs"
    drive_root.mkdir(parents=True, exist_ok=True)
    job_root.mkdir(parents=True, exist_ok=True)

    state_path = job_root / "cloudflared_state.json"
    state_path.write_text(
        json.dumps(
            {
                "pid": 999999,
                "url": "https://example.trycloudflare.com",
                "server_url": "http://127.0.0.1:8000",
            }
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["ALLOWED_ROOTS"] = f"{content_root},{drive_root}"
    env["JOB_WORK_DIR"] = str(job_root)

    result = subprocess.run(
        [sys.executable, "scripts/stop_tunnel.py"],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "was already stopped or unavailable" in result.stdout
    assert "Removed stale tunnel state." in result.stdout
    assert not state_path.exists()


def test_stop_server_is_idempotent_for_stale_pid(tmp_path: Path):
    content_root = tmp_path / "content"
    drive_root = content_root / "drive" / "MyDrive"
    job_root = content_root / ".colab_full_control_mcp" / "jobs"
    drive_root.mkdir(parents=True, exist_ok=True)
    job_root.mkdir(parents=True, exist_ok=True)

    pid_path = job_root / "mcp_server.pid"
    pid_path.write_text("999999", encoding="utf-8")

    env = os.environ.copy()
    env["ALLOWED_ROOTS"] = f"{content_root},{drive_root}"
    env["JOB_WORK_DIR"] = str(job_root)

    result = subprocess.run(
        [sys.executable, "scripts/stop_server.py"],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "was already stopped or unavailable" in result.stdout
    assert "Removed stale PID file." in result.stdout
    assert not pid_path.exists()


def test_extract_tunnel_url_finds_trycloudflare_url():
    text = "INF Starting tunnel\nhttps://example-name.trycloudflare.com connected\n"
    assert extract_tunnel_url(text) == "https://example-name.trycloudflare.com"
