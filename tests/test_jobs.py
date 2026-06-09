from __future__ import annotations

import sys
import time
from pathlib import Path

import psutil

from conftest import TEST_TOKEN


def test_job_lifecycle_and_logs(bundle):
    response = bundle.model_tools.start_job(
        [sys.executable, "-c", "print('job-start'); print('job-end')"],
        working_directory=bundle.settings.allowed_roots[0],
        token=TEST_TOKEN,
    )
    assert response["ok"] is True
    job_id = response["data"]["job_id"]
    finished = bundle.model_tools.wait_for_job(job_id, timeout_seconds=10)
    assert finished["ok"] is True
    assert finished["data"]["status"] in {"completed", "failed"}
    logs = bundle.model_tools.get_job_logs(job_id)
    assert "job-start" in logs["data"]["content"]


def test_process_group_termination(bundle):
    root = Path(bundle.settings.allowed_roots[0])
    child_pid_path = root / "child.pid"
    code = (
        "import pathlib, subprocess, sys, time; "
        f"p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
        f"pathlib.Path(r'{child_pid_path}').write_text(str(p.pid)); "
        "time.sleep(30)"
    )
    started = bundle.model_tools.start_job([sys.executable, "-c", code], working_directory=str(root), token=TEST_TOKEN)
    assert started["ok"] is True
    job_id = started["data"]["job_id"]
    for _ in range(30):
        if child_pid_path.exists():
            break
        time.sleep(0.1)
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    stopped = bundle.model_tools.stop_job(job_id, token=TEST_TOKEN, confirm=True)
    assert stopped["ok"] is True
    time.sleep(0.5)
    assert not psutil.pid_exists(child_pid)
