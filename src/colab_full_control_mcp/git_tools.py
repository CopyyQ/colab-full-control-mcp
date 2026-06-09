from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .base import BaseToolset, ToolPayload
from .common import ExecutionError, ValidationError, current_env_subset, sanitize_text
from .path_manager import PathManager
from .permissions import PermissionProfile


class GitTools(BaseToolset):
    def __init__(self, *, path_manager: PathManager, **kwargs: Any):
        super().__init__(**kwargs)
        self.path_manager = path_manager

    def _repo_path(self, repo_path: str | None) -> Path:
        return self.path_manager.resolve_root(repo_path)

    def _run_git(self, repo_path: str | None, args: list[str], timeout: int = 300) -> ToolPayload:
        repo = self._repo_path(repo_path)
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo),
            env=current_env_subset(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        stdout, stdout_truncated = sanitize_text(result.stdout, self.settings.max_text_output_chars)
        stderr, stderr_truncated = sanitize_text(result.stderr, self.settings.max_text_output_chars)
        return ToolPayload(
            {"repo_path": str(repo), "args": args, "returncode": result.returncode, "stdout": stdout, "stderr": stderr},
            truncated=stdout_truncated or stderr_truncated,
        )

    def git_status(self, repo_path: str | None = None) -> dict[str, Any]:
        return self._invoke(tool_name="git_status", action_category="read", operation=lambda: self._run_git(repo_path, ["status", "--short", "--branch"]), args={"repo_path": repo_path}, paths=[repo_path] if repo_path else None)

    def git_diff(self, repo_path: str | None = None, cached: bool = False) -> dict[str, Any]:
        args = ["diff"]
        if cached:
            args.append("--cached")
        return self._invoke(tool_name="git_diff", action_category="read", operation=lambda: self._run_git(repo_path, args), args={"repo_path": repo_path, "cached": cached}, paths=[repo_path] if repo_path else None)

    def git_log(self, repo_path: str | None = None, max_count: int = 20) -> dict[str, Any]:
        return self._invoke(tool_name="git_log", action_category="read", operation=lambda: self._run_git(repo_path, ["log", f"--max-count={max_count}", "--oneline", "--decorate"]), args={"repo_path": repo_path, "max_count": max_count}, paths=[repo_path] if repo_path else None)

    def git_branch(self, repo_path: str | None = None) -> dict[str, Any]:
        return self._invoke(tool_name="git_branch", action_category="read", operation=lambda: self._run_git(repo_path, ["branch", "--all", "--verbose"]), args={"repo_path": repo_path}, paths=[repo_path] if repo_path else None)

    def git_checkout(self, branch: str, repo_path: str | None = None, create: bool = False, token: str | None = None, confirm: bool = False) -> dict[str, Any]:
        args = ["checkout"]
        if create:
            args.append("-b")
        args.append(branch)
        return self._invoke(tool_name="git_checkout", action_category="execute", operation=lambda: self._run_git(repo_path, args), min_profile=PermissionProfile.DEVELOPER, token=token, confirm=confirm, args={"repo_path": repo_path, "branch": branch, "create": create}, paths=[repo_path] if repo_path else None)

    def git_create_branch(self, branch: str, repo_path: str | None = None, token: str | None = None) -> dict[str, Any]:
        return self.git_checkout(branch=branch, repo_path=repo_path, create=True, token=token)

    def git_add(self, repo_path: str | None = None, paths: list[str] | None = None, token: str | None = None) -> dict[str, Any]:
        args = ["add", *(paths or ["."])]
        return self._invoke(tool_name="git_add", action_category="execute", operation=lambda: self._run_git(repo_path, args), min_profile=PermissionProfile.DEVELOPER, token=token, args={"repo_path": repo_path, "paths": paths}, paths=paths)

    def git_commit(self, message: str, repo_path: str | None = None, token: str | None = None) -> dict[str, Any]:
        if not message.strip():
            raise ValidationError("Commit message must not be empty")
        return self._invoke(tool_name="git_commit", action_category="execute", operation=lambda: self._run_git(repo_path, ["commit", "-m", message]), min_profile=PermissionProfile.DEVELOPER, token=token, args={"repo_path": repo_path, "message": message}, paths=[repo_path] if repo_path else None)

    def git_pull(self, repo_path: str | None = None, remote: str = "origin", branch: str | None = None, token: str | None = None) -> dict[str, Any]:
        args = ["pull", remote]
        if branch:
            args.append(branch)
        return self._invoke(tool_name="git_pull", action_category="execute", operation=lambda: self._run_git(repo_path, args), min_profile=PermissionProfile.DEVELOPER, token=token, args={"repo_path": repo_path, "remote": remote, "branch": branch}, paths=[repo_path] if repo_path else None)

    def git_push(self, repo_path: str | None = None, remote: str = "origin", branch: str | None = None, force: bool = False, token: str | None = None, confirm: bool = False) -> dict[str, Any]:
        args = ["push", remote]
        if branch:
            args.append(branch)
        if force:
            args.append("--force")
        return self._invoke(tool_name="git_push", action_category="execute", operation=lambda: self._run_git(repo_path, args), min_profile=PermissionProfile.DEVELOPER, token=token, confirm=confirm, destructive=force, args={"repo_path": repo_path, "remote": remote, "branch": branch, "force": force}, paths=[repo_path] if repo_path else None)

    def git_clone(self, repo_url: str, destination_path: str, token: str | None = None) -> dict[str, Any]:
        def operation() -> ToolPayload:
            destination = self.path_manager.resolve_path(destination_path, allow_missing=True)
            result = subprocess.run(
                ["git", "clone", repo_url, str(destination)],
                cwd=str(destination.parent),
                env=current_env_subset(),
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            stdout, stdout_truncated = sanitize_text(result.stdout, self.settings.max_text_output_chars)
            stderr, stderr_truncated = sanitize_text(result.stderr, self.settings.max_text_output_chars)
            return ToolPayload(
                {"repo_url": repo_url, "destination_path": str(destination), "returncode": result.returncode, "stdout": stdout, "stderr": stderr},
                truncated=stdout_truncated or stderr_truncated,
            )

        return self._invoke(tool_name="git_clone", action_category="execute", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"repo_url": repo_url, "destination_path": destination_path}, paths=[destination_path])

    def git_fetch(self, repo_path: str | None = None, remote: str | None = None, token: str | None = None) -> dict[str, Any]:
        args = ["fetch"]
        if remote:
            args.append(remote)
        return self._invoke(tool_name="git_fetch", action_category="execute", operation=lambda: self._run_git(repo_path, args), min_profile=PermissionProfile.DEVELOPER, token=token, args={"repo_path": repo_path, "remote": remote}, paths=[repo_path] if repo_path else None)

    def git_merge(self, branch: str, repo_path: str | None = None, token: str | None = None) -> dict[str, Any]:
        return self._invoke(tool_name="git_merge", action_category="execute", operation=lambda: self._run_git(repo_path, ["merge", branch]), min_profile=PermissionProfile.DEVELOPER, token=token, args={"repo_path": repo_path, "branch": branch}, paths=[repo_path] if repo_path else None)

    def git_stash(self, repo_path: str | None = None, message: str | None = None, token: str | None = None) -> dict[str, Any]:
        args = ["stash"]
        if message:
            args.extend(["push", "-m", message])
        return self._invoke(tool_name="git_stash", action_category="execute", operation=lambda: self._run_git(repo_path, args), min_profile=PermissionProfile.DEVELOPER, token=token, args={"repo_path": repo_path, "message": message}, paths=[repo_path] if repo_path else None)

    def git_restore(self, repo_path: str | None = None, paths: list[str] | None = None, staged: bool = False, token: str | None = None, confirm: bool = False) -> dict[str, Any]:
        args = ["restore"]
        if staged:
            args.append("--staged")
        args.extend(paths or ["."])
        return self._invoke(tool_name="git_restore", action_category="execute", operation=lambda: self._run_git(repo_path, args), min_profile=PermissionProfile.DEVELOPER, token=token, confirm=confirm, destructive=True, args={"repo_path": repo_path, "paths": paths, "staged": staged}, paths=paths or ([repo_path] if repo_path else None))

