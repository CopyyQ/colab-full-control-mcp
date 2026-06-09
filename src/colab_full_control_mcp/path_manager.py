from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote

from .common import PathSafetyError, ensure_directory


class PathManager:
    _ALWAYS_BLOCKED = [
        "/proc",
        "/sys",
        "/etc",
        "/dev",
        "/var/run/secrets",
        "/root/.config",
        "/.dockerenv",
        "169.254.169.254",
        "metadata.google.internal",
    ]

    def __init__(self, allowed_roots: list[Path], unrestricted_runtime_mode: bool = False):
        if not allowed_roots:
            raise ValueError("allowed_roots must not be empty")
        self.allowed_roots = [root.expanduser().resolve(strict=False) for root in allowed_roots]
        self.primary_root = self.allowed_roots[0]
        self.unrestricted_runtime_mode = unrestricted_runtime_mode

    def allowed_root_strings(self) -> list[str]:
        return [str(root) for root in self.allowed_roots]

    def ensure_allowed_roots(self) -> None:
        for root in self.allowed_roots:
            ensure_directory(root)

    def _decode(self, raw_path: str | Path) -> str:
        if isinstance(raw_path, Path):
            raw = str(raw_path)
        else:
            raw = raw_path
        decoded = unquote(raw)
        if "\x00" in decoded:
            raise PathSafetyError("Null bytes are not allowed in paths")
        return decoded

    def _is_blocked_system_path(self, path: Path) -> bool:
        text = str(path).replace("\\", "/")
        return any(text == blocked or text.startswith(blocked + "/") for blocked in self._ALWAYS_BLOCKED)

    def _check_allowed(self, resolved: Path) -> None:
        if self._is_blocked_system_path(resolved):
            raise PathSafetyError(f"Access to system path is blocked: {resolved}")
        if self.unrestricted_runtime_mode:
            return
        for root in self.allowed_roots:
            try:
                resolved.relative_to(root)
                return
            except ValueError:
                continue
        raise PathSafetyError(
            "Path is outside allowed roots",
            {"path": str(resolved), "allowed_roots": self.allowed_root_strings()},
        )

    def resolve_path(self, raw_path: str | Path, *, allow_missing: bool = False) -> Path:
        decoded = self._decode(raw_path)
        candidate = Path(decoded).expanduser()
        if not candidate.is_absolute():
            candidate = self.primary_root / candidate

        if candidate.exists():
            resolved = candidate.resolve(strict=True)
            self._check_allowed(resolved)
            return resolved

        if not allow_missing:
            raise PathSafetyError(f"Path does not exist: {candidate}")

        parent = candidate.parent
        if not parent.exists():
            resolved_parent = parent.resolve(strict=False)
        else:
            resolved_parent = parent.resolve(strict=True)
        self._check_allowed(resolved_parent)
        resolved = (resolved_parent / candidate.name).resolve(strict=False)
        self._check_allowed(resolved)
        return resolved

    def resolve_root(self, raw_path: str | Path | None = None) -> Path:
        if raw_path is None:
            return self.primary_root
        return self.resolve_path(raw_path)

