from __future__ import annotations

import subprocess
from pathlib import Path

from conftest import TEST_TOKEN


def test_git_status_and_force_push_confirmation(bundle):
    repo = Path(bundle.settings.allowed_roots[0]) / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True, capture_output=True)
    (repo / "main.py").write_text("print('hi')\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

    status = bundle.git_tools.git_status(str(repo))
    assert status["ok"] is True
    assert "master" in status["data"]["stdout"] or "main" in status["data"]["stdout"]

    force_push = bundle.git_tools.git_push(str(repo), force=True, token=TEST_TOKEN, confirm=False)
    assert force_push["ok"] is False
    assert force_push["error"]["type"] == "confirmation_required"
