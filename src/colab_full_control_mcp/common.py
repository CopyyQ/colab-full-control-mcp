from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_MESSAGE = "OK"


def make_request_id() -> str:
    return uuid.uuid4().hex


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def ok_response(
    data: Any | None = None,
    *,
    message: str = DEFAULT_MESSAGE,
    request_id: str | None = None,
    truncated: bool = False,
) -> dict[str, Any]:
    return {
        "ok": True,
        "data": _json_safe(data or {}),
        "message": message,
        "request_id": request_id or make_request_id(),
        "truncated": truncated,
    }


def error_response(
    error_type: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "type": error_type,
            "message": message,
            "details": _json_safe(details or {}),
        },
        "request_id": request_id or make_request_id(),
    }


class MCPToolError(Exception):
    def __init__(self, error_type: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.error_type = error_type
        self.details = details or {}

    def to_response(self, request_id: str | None = None) -> dict[str, Any]:
        return error_response(self.error_type, str(self), details=self.details, request_id=request_id)


class AuthError(MCPToolError):
    def __init__(self, message: str = "Authentication failed", details: dict[str, Any] | None = None):
        super().__init__("auth_error", message, details)


class PermissionError(MCPToolError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__("permission_denied", message, details)


class ValidationError(MCPToolError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__("validation_error", message, details)


class PathSafetyError(MCPToolError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__("path_safety_error", message, details)


class ExecutionError(MCPToolError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__("execution_error", message, details)


class ConfirmationRequiredError(MCPToolError):
    def __init__(self, message: str = "This operation requires confirm=true"):
        super().__init__("confirmation_required", message, {})


SECRET_KEY_RE = re.compile(r"(token|secret|password|passwd|api[_-]?key|credential)", re.IGNORECASE)


def sanitize_mapping(mapping: dict[str, Any] | None) -> dict[str, Any]:
    if not mapping:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in mapping.items():
        if SECRET_KEY_RE.search(str(key)):
            cleaned[str(key)] = "[REDACTED]"
        else:
            cleaned[str(key)] = _json_safe(value)
    return cleaned


def sanitize_text(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def sanitize_command_parts(parts: list[str]) -> list[str]:
    return ["[REDACTED]" if SECRET_KEY_RE.search(part) else part for part in parts]


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def bool_from_env(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def current_env_subset(extra: dict[str, str] | None = None) -> dict[str, str]:
    base_keys = ["PATH", "PYTHONPATH", "HOME", "USER", "LANG", "LC_ALL", "SHELL", "SYSTEMROOT", "TEMP", "TMP"]
    env = {key: os.environ[key] for key in base_keys if key in os.environ}
    if extra:
        env.update(extra)
    return env


@dataclass(slots=True)
class ToolRunContext:
    tool_name: str
    request_id: str
    action_category: str

