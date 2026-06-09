from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from .base import BaseToolset, ToolPayload
from .common import ExecutionError, ValidationError, current_env_subset, sanitize_command_parts, sanitize_text
from .job_manager import JobManager
from .path_manager import PathManager
from .permissions import PermissionProfile


class ShellTools(BaseToolset):
    SAFE_ALLOWLIST = {
        "python",
        "python3",
        "pip",
        "pip3",
        "git",
        "pytest",
        "ls",
        "pwd",
        "find",
        "grep",
        "rg",
        "cat",
        "head",
        "tail",
        "sed",
        "awk",
        "cp",
        "mv",
        "mkdir",
        "touch",
        "nvidia-smi",
        "ps",
        "kill",
        "tar",
        "unzip",
        "zip",
        "du",
        "df",
    }

    ALWAYS_BLOCKED_PATTERNS = [
        r"\bshutdown\b",
        r"\breboot\b",
        r"\bpoweroff\b",
        r"\bhalt\b",
        r"\bmkfs\b",
        r"\bfdisk\b",
        r"\bparted\b",
        r"\bdd\s+.*(/dev/|PhysicalDrive)",
        r"169\.254\.169\.254",
        r"metadata\.google\.internal",
        r"\bcurl\b.*\|\s*(bash|sh)",
        r"\bwget\b.*\|\s*(bash|sh)",
        r"/proc\b",
        r"/sys\b",
        r"/etc\b",
    ]

    CONFIRM_REQUIRED_PATTERNS = [
        r"\brm\s+-rf\b",
        r"\bgit\s+reset\s+--hard\b",
        r"\bgit\s+clean\b",
        r"\bkill\s+-9\b",
        r"\bpip\s+uninstall\b",
        r"\bgit\s+push\b.*--force",
    ]

    def __init__(self, *, path_manager: PathManager, job_manager: JobManager, **kwargs: Any):
        super().__init__(**kwargs)
        self.path_manager = path_manager
        self.job_manager = job_manager

    def _validate_working_directory(self, working_directory: str | None) -> str:
        if working_directory is None:
            return str(self.path_manager.primary_root)
        return str(self.path_manager.resolve_path(working_directory))

    def _run_foreground(self, command: list[str], cwd: str, timeout: int, env: dict[str, str], stdin: str | None = None) -> ToolPayload:
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                input=stdin,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ExecutionError("Command timed out", {"timeout": timeout}) from exc
        stdout, stdout_truncated = sanitize_text(result.stdout, self.settings.max_text_output_chars)
        stderr, stderr_truncated = sanitize_text(result.stderr, self.settings.max_text_output_chars)
        return ToolPayload(
            {
                "command": sanitize_command_parts(command),
                "cwd": cwd,
                "returncode": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
            },
            truncated=stdout_truncated or stderr_truncated,
        )

    def run_safe_command(
        self,
        command: list[str],
        working_directory: str | None = None,
        timeout: int = 300,
        background: bool = False,
        log_path: str | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        def operation() -> dict[str, Any] | ToolPayload:
            if not command:
                raise ValidationError("command must not be empty")
            executable = Path(command[0]).stem.lower()
            if executable not in self.SAFE_ALLOWLIST:
                raise ValidationError("Command is not in the safe allowlist", {"command": executable})
            cwd = self._validate_working_directory(working_directory)
            env = current_env_subset()
            if background:
                return self.job_manager.start_job(command=command, cwd=cwd, env=env, kind="safe-shell", log_path=log_path)
            return self._run_foreground(command, cwd, timeout, env)

        return self._invoke(tool_name="run_safe_command", action_category="execute", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"command": sanitize_command_parts(command), "working_directory": working_directory, "timeout": timeout, "background": background})

    def run_shell_command(
        self,
        command: str,
        working_directory: str | None = None,
        timeout: int = 300,
        background: bool = False,
        confirm: bool = False,
        token: str | None = None,
    ) -> dict[str, Any]:
        def operation() -> dict[str, Any] | ToolPayload:
            normalized = command.strip()
            if not normalized:
                raise ValidationError("command must not be empty")
            for pattern in self.ALWAYS_BLOCKED_PATTERNS:
                if re.search(pattern, normalized, re.IGNORECASE):
                    raise ValidationError("Blocked shell command pattern detected", {"pattern": pattern})
            for pattern in self.CONFIRM_REQUIRED_PATTERNS:
                if re.search(pattern, normalized, re.IGNORECASE) and not confirm:
                    raise ValidationError("This shell command requires confirm=true", {"pattern": pattern})
            cwd = self._validate_working_directory(working_directory)
            env = current_env_subset()
            if os.name == "nt":
                command_list = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", normalized]
            else:
                command_list = ["/bin/bash", "-lc", normalized]
            if background:
                return self.job_manager.start_job(command=command_list, cwd=cwd, env=env, kind="shell", log_path=log_path)
            return self._run_foreground(command_list, cwd, timeout, env)

        return self._invoke(tool_name="run_shell_command", action_category="execute", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, confirm=confirm, args={"command": command, "working_directory": working_directory, "timeout": timeout, "background": background})
