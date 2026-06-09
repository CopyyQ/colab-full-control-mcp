from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from colab_full_control_mcp.settings import Settings
from colab_full_control_mcp.tools import ToolBundle, build_tool_bundle


TEST_TOKEN = "test-token"


@pytest.fixture
def settings_factory(tmp_path: Path):
    def factory(*, permission_profile: str = "FULL_CONTROL", max_read_bytes: int = 120, max_text_output_chars: int = 2000) -> Settings:
        content_root = tmp_path / "content"
        drive_root = content_root / "drive" / "MyDrive"
        content_root.mkdir(parents=True, exist_ok=True)
        drive_root.mkdir(parents=True, exist_ok=True)
        return Settings(
            colab_mcp_token=TEST_TOKEN,
            permission_profile=permission_profile,
            allowed_roots=[str(content_root), str(drive_root)],
            unrestricted_runtime_mode=False,
            host="127.0.0.1",
            port=8000,
            mount_path="/mcp",
            audit_log_path=str(tmp_path / "audit.jsonl"),
            job_db_path=str(tmp_path / "jobs.sqlite3"),
            job_work_dir=str(tmp_path / "job-work"),
            session_work_dir=str(tmp_path / "sessions"),
            max_read_bytes=max_read_bytes,
            max_text_output_chars=max_text_output_chars,
        )

    return factory


@pytest.fixture
def bundle(settings_factory) -> ToolBundle:
    built = build_tool_bundle(settings_factory())
    yield built
    for session_id in list(built.session_manager.sessions):
        try:
            built.session_manager.close(session_id)
        except Exception:
            pass
