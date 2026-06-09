from __future__ import annotations

import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .base import BaseToolset, ToolPayload
from .common import ExecutionError, SECRET_KEY_RE, ValidationError, current_env_subset
from .job_manager import JobManager
from .path_manager import PathManager
from .permissions import PermissionProfile
from .shell_tools import ShellTools


class PythonTools(BaseToolset):
    def __init__(self, *, path_manager: PathManager, job_manager: JobManager, **kwargs: Any):
        super().__init__(**kwargs)
        self.path_manager = path_manager
        self.job_manager = job_manager
        self.shell_tools = ShellTools(path_manager=path_manager, job_manager=job_manager, settings=self.settings, auth_manager=self.auth_manager, permission_manager=self.permission_manager, audit_logger=self.audit_logger)

    def _safe_env(self, overrides: dict[str, str] | None) -> dict[str, str]:
        env = current_env_subset()
        if not overrides:
            return env
        for key, value in overrides.items():
            if SECRET_KEY_RE.search(key):
                raise ValidationError("Environment overrides must not include secret-like keys", {"key": key})
            env[key] = str(value)
        return env

    def _foreground(self, command: list[str], cwd: str, timeout: int, env: dict[str, str], stdin: str | None = None) -> ToolPayload:
        return self.shell_tools._run_foreground(command, cwd, timeout, env, stdin=stdin)

    def run_python_code(
        self,
        code: str,
        working_directory: str | None = None,
        environment: dict[str, str] | None = None,
        timeout: int = 300,
        stdin: str | None = None,
        background: bool = False,
        log_path: str | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        def operation() -> dict[str, Any] | ToolPayload:
            cwd = str(self.path_manager.resolve_root(working_directory))
            env = self._safe_env(environment)
            command = [sys.executable, "-c", code]
            if background:
                return self.job_manager.start_job(command=command, cwd=cwd, env=env, kind="python-code", log_path=log_path)
            return self._foreground(command, cwd, timeout, env, stdin=stdin)

        return self._invoke(tool_name="run_python_code", action_category="execute", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"working_directory": working_directory, "timeout": timeout, "background": background})

    def run_python_file(
        self,
        script_path: str,
        working_directory: str | None = None,
        arguments: list[str] | None = None,
        environment: dict[str, str] | None = None,
        timeout: int = 300,
        stdin: str | None = None,
        background: bool = False,
        log_path: str | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        def operation() -> dict[str, Any] | ToolPayload:
            script = self.path_manager.resolve_path(script_path)
            cwd = str(self.path_manager.resolve_root(working_directory or str(script.parent)))
            env = self._safe_env(environment)
            command = [sys.executable, str(script), *(arguments or [])]
            if background:
                return self.job_manager.start_job(command=command, cwd=cwd, env=env, kind="python-file", log_path=log_path)
            return self._foreground(command, cwd, timeout, env, stdin=stdin)

        return self._invoke(tool_name="run_python_file", action_category="execute", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"script_path": script_path, "working_directory": working_directory, "timeout": timeout, "background": background}, paths=[script_path])

    def run_python_module(
        self,
        module: str,
        working_directory: str | None = None,
        arguments: list[str] | None = None,
        environment: dict[str, str] | None = None,
        timeout: int = 300,
        background: bool = False,
        log_path: str | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        def operation() -> dict[str, Any] | ToolPayload:
            cwd = str(self.path_manager.resolve_root(working_directory))
            env = self._safe_env(environment)
            command = [sys.executable, "-m", module, *(arguments or [])]
            if background:
                return self.job_manager.start_job(command=command, cwd=cwd, env=env, kind="python-module", log_path=log_path)
            return self._foreground(command, cwd, timeout, env)

        return self._invoke(tool_name="run_python_module", action_category="execute", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"module": module, "working_directory": working_directory, "timeout": timeout, "background": background})

    def run_pytest(
        self,
        working_directory: str | None = None,
        paths: list[str] | None = None,
        extra_args: list[str] | None = None,
        timeout: int = 600,
        background: bool = False,
        log_path: str | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        def operation() -> dict[str, Any] | ToolPayload:
            cwd = str(self.path_manager.resolve_root(working_directory))
            resolved_paths = [str(self.path_manager.resolve_path(path)) for path in paths] if paths else []
            command = [sys.executable, "-m", "pytest", *resolved_paths, *(extra_args or [])]
            env = self._safe_env(None)
            if background:
                return self.job_manager.start_job(command=command, cwd=cwd, env=env, kind="pytest", log_path=log_path)
            return self._foreground(command, cwd, timeout, env)

        return self._invoke(tool_name="run_pytest", action_category="execute", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"working_directory": working_directory, "paths": paths, "extra_args": extra_args, "timeout": timeout, "background": background}, paths=paths)

    def run_unit_test(self, test_path: str, test_name: str | None = None, timeout: int = 600, token: str | None = None) -> dict[str, Any]:
        selector = str(self.path_manager.resolve_path(test_path))
        if test_name:
            selector = f"{selector}::{test_name}"
        return self.run_pytest(paths=[selector], timeout=timeout, token=token)

    def run_import_check(self, import_target: str, token: str | None = None, timeout: int = 120) -> dict[str, Any]:
        code = f"import importlib; importlib.import_module({import_target!r}); print('OK')"
        return self.run_python_code(code=code, timeout=timeout, token=token)

    def run_compile_check(self, root_path: str, token: str | None = None, timeout: int = 600) -> dict[str, Any]:
        root = self.path_manager.resolve_root(root_path)
        return self.run_python_module(module="compileall", working_directory=str(root), arguments=["-q", str(root)], timeout=timeout, token=token)

    def list_installed_packages(self) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            packages = sorted((dist.metadata["Name"], dist.version) for dist in importlib.metadata.distributions())
            return {"packages": [{"name": name, "version": version} for name, version in packages]}

        return self._invoke(tool_name="list_installed_packages", action_category="read", operation=operation)

    def check_package_version(self, package_name: str) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            try:
                version = importlib.metadata.version(package_name)
            except importlib.metadata.PackageNotFoundError as exc:
                raise ValidationError("Package is not installed", {"package_name": package_name}) from exc
            return {"package_name": package_name, "version": version}

        return self._invoke(tool_name="check_package_version", action_category="read", operation=operation, args={"package_name": package_name})

    def install_python_packages(
        self,
        packages: list[str],
        token: str | None = None,
        upgrade: bool = False,
        index_url: str | None = None,
        confirm: bool = False,
        timeout: int = 1800,
    ) -> dict[str, Any]:
        def operation() -> ToolPayload:
            if not packages:
                raise ValidationError("packages must not be empty")
            command = [sys.executable, "-m", "pip", "install"]
            if upgrade:
                command.append("--upgrade")
            if index_url:
                if not confirm:
                    raise ValidationError("Custom index_url requires confirm=true")
                command.extend(["--index-url", index_url])
            command.extend(packages)
            env = self._safe_env(None)
            return self._foreground(command, str(self.path_manager.primary_root), timeout, env)

        return self._invoke(tool_name="install_python_packages", action_category="execute", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, confirm=confirm, args={"packages": packages, "upgrade": upgrade, "index_url": bool(index_url), "timeout": timeout})

    def uninstall_python_packages(self, packages: list[str], token: str | None = None, confirm: bool = False, timeout: int = 1800) -> dict[str, Any]:
        def operation() -> ToolPayload:
            if not packages:
                raise ValidationError("packages must not be empty")
            command = [sys.executable, "-m", "pip", "uninstall", "-y", *packages]
            env = self._safe_env(None)
            return self._foreground(command, str(self.path_manager.primary_root), timeout, env)

        return self._invoke(tool_name="uninstall_python_packages", action_category="execute", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, confirm=confirm, destructive=True, args={"packages": packages, "timeout": timeout})

    def install_requirements(self, requirements_path: str, token: str | None = None, timeout: int = 1800, confirm: bool = False) -> dict[str, Any]:
        def operation() -> ToolPayload:
            target = self.path_manager.resolve_path(requirements_path)
            command = [sys.executable, "-m", "pip", "install", "-r", str(target)]
            env = self._safe_env(None)
            return self._foreground(command, str(target.parent), timeout, env)

        return self._invoke(tool_name="install_requirements", action_category="execute", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, confirm=confirm, args={"requirements_path": requirements_path, "timeout": timeout}, paths=[requirements_path])
