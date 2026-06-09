from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .common import bool_from_env


@dataclass(slots=True)
class Settings:
    colab_mcp_token: str = field(default_factory=lambda: os.getenv("COLAB_MCP_TOKEN", ""))
    permission_profile: str = field(default_factory=lambda: os.getenv("PERMISSION_PROFILE", "DEVELOPER").upper())
    allowed_roots: list[str] = field(
        default_factory=lambda: [
            item.strip()
            for item in os.getenv("ALLOWED_ROOTS", "/content,/content/drive/MyDrive").split(",")
            if item.strip()
        ]
    )
    unrestricted_runtime_mode: bool = field(
        default_factory=lambda: bool_from_env(os.getenv("UNRESTRICTED_RUNTIME_MODE"), False)
    )
    host: str = field(default_factory=lambda: os.getenv("MCP_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("MCP_PORT", "8000")))
    mount_path: str = field(default_factory=lambda: os.getenv("MCP_MOUNT_PATH", "/mcp"))
    audit_log_path: str = field(
        default_factory=lambda: os.getenv("AUDIT_LOG_PATH", "/content/colab_full_control_mcp_audit.jsonl")
    )
    job_db_path: str = field(
        default_factory=lambda: os.getenv("JOB_DB_PATH", "/content/colab_full_control_mcp_jobs.sqlite3")
    )
    job_work_dir: str = field(
        default_factory=lambda: os.getenv("JOB_WORK_DIR", "/content/.colab_full_control_mcp/jobs")
    )
    session_work_dir: str = field(
        default_factory=lambda: os.getenv("SESSION_WORK_DIR", "/content/.colab_full_control_mcp/sessions")
    )
    max_read_bytes: int = field(default_factory=lambda: int(os.getenv("MAX_READ_BYTES", "200000")))
    max_text_output_chars: int = field(default_factory=lambda: int(os.getenv("MAX_TEXT_OUTPUT_CHARS", "40000")))

    def allowed_root_paths(self) -> list[Path]:
        return [Path(path).expanduser() for path in self.allowed_roots]

    @property
    def audit_log(self) -> Path:
        return Path(self.audit_log_path).expanduser()

    @property
    def job_db(self) -> Path:
        return Path(self.job_db_path).expanduser()

    @property
    def job_root(self) -> Path:
        return Path(self.job_work_dir).expanduser()

    @property
    def session_root(self) -> Path:
        return Path(self.session_work_dir).expanduser()

