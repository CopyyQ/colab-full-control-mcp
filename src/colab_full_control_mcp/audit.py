from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .common import ensure_directory, sanitize_mapping


class AuditLogger:
    def __init__(self, log_path: Path):
        self.log_path = log_path.expanduser()
        ensure_directory(self.log_path.parent)

    def write(
        self,
        *,
        request_id: str,
        tool: str,
        action_category: str,
        args: dict[str, Any] | None = None,
        paths: list[str] | None = None,
        job_id: str | None = None,
        duration_ms: int | None = None,
        success: bool,
        error: str | None = None,
    ) -> None:
        record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "request_id": request_id,
            "tool": tool,
            "action_category": action_category,
            "sanitized_args": sanitize_mapping(args),
            "paths": paths or [],
            "job_id": job_id,
            "duration_ms": duration_ms,
            "success": success,
            "error": error,
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
