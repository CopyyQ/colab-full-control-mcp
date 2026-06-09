from __future__ import annotations

import fnmatch
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import nbformat

from .base import BaseToolset, ToolPayload
from .common import ExecutionError, ValidationError, sanitize_text
from .path_manager import PathManager
from .permissions import PermissionProfile


class CodeTools(BaseToolset):
    def __init__(self, *, path_manager: PathManager, **kwargs: Any):
        super().__init__(**kwargs)
        self.path_manager = path_manager

    def search_code(
        self,
        root_path: str,
        query: str,
        file_globs: list[str] | None = None,
        regex: bool = False,
        case_sensitive: bool = False,
        max_results: int = 50,
        context_lines: int = 2,
    ) -> dict[str, Any]:
        import re

        def operation() -> dict[str, Any]:
            root = self.path_manager.resolve_root(root_path)
            patterns = file_globs or ["*.py", "*.ipynb", "*.md", "*.toml", "*.yaml", "*.yml", "*.json", "*.txt"]
            flags = 0 if case_sensitive else re.IGNORECASE
            compiled = re.compile(query, flags) if regex else None
            results: list[dict[str, Any]] = []
            for file_path in root.rglob("*"):
                if not file_path.is_file():
                    continue
                rel = file_path.relative_to(root)
                if not any(fnmatch.fnmatch(str(rel), pattern) for pattern in patterns):
                    continue
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                lines = content.splitlines()
                for index, line in enumerate(lines):
                    matched = bool(compiled.search(line)) if regex else (query in line if case_sensitive else query.lower() in line.lower())
                    if not matched:
                        continue
                    start = max(index - context_lines, 0)
                    end = min(index + context_lines + 1, len(lines))
                    results.append(
                        {
                            "path": str(file_path),
                            "line_number": index + 1,
                            "line": line,
                            "context": lines[start:end],
                        }
                    )
                    if len(results) >= max_results:
                        return {"root": str(root), "results": results}
            return {"root": str(root), "results": results}

        return self._invoke(tool_name="search_code", action_category="read", operation=operation, args={"root_path": root_path, "query": query, "file_globs": file_globs, "regex": regex, "case_sensitive": case_sensitive, "max_results": max_results})

    def read_project(self, root_path: str, page: int = 1, page_size: int = 20, max_chars_per_file: int = 4000) -> dict[str, Any]:
        def operation() -> ToolPayload:
            root = self.path_manager.resolve_root(root_path)
            files: list[Path] = []
            preferred_names = {"pyproject.toml", "requirements.txt", "README.md", "README", "config.toml", "config.example.toml"}
            for file_path in root.rglob("*"):
                if not file_path.is_file():
                    continue
                if file_path.name in preferred_names or file_path.suffix in {".py", ".toml", ".json", ".yaml", ".yml", ".md", ".ipynb"}:
                    files.append(file_path)
            files = sorted(files, key=lambda path: (path.name not in preferred_names, str(path)))
            total = len(files)
            start = max(page - 1, 0) * page_size
            page_files = files[start : start + page_size]
            entries = []
            truncated = False
            for file_path in page_files:
                if file_path.suffix == ".ipynb":
                    notebook = nbformat.read(file_path, as_version=4)
                    preview = json.dumps({"metadata": notebook.metadata, "cell_count": len(notebook.cells)})
                else:
                    preview = file_path.read_text(encoding="utf-8", errors="replace")
                preview, item_truncated = sanitize_text(preview, max_chars_per_file)
                truncated = truncated or item_truncated
                entries.append({"path": str(file_path), "preview": preview, "truncated": item_truncated})
            return ToolPayload(
                {
                    "root": str(root),
                    "page": page,
                    "page_size": page_size,
                    "total_files": total,
                    "entries": entries,
                },
                truncated=truncated,
            )

        return self._invoke(tool_name="read_project", action_category="read", operation=operation, args={"root_path": root_path, "page": page, "page_size": page_size, "max_chars_per_file": max_chars_per_file})

    def format_code(self, paths: list[str], token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            resolved_paths = [str(self.path_manager.resolve_path(path)) for path in paths]
            executed: list[list[str]] = []

            if shutil.which("ruff"):
                command = ["ruff", "format", *resolved_paths]
                subprocess.run(command, check=True, capture_output=True, text=True)
                executed.append(command)
            elif shutil.which("black"):
                command = ["black", *resolved_paths]
                subprocess.run(command, check=True, capture_output=True, text=True)
                executed.append(command)

            if shutil.which("isort"):
                command = ["isort", *resolved_paths]
                subprocess.run(command, check=True, capture_output=True, text=True)
                executed.append(command)

            if not executed:
                raise ExecutionError("No supported formatter is installed (ruff, black, isort)")

            return {"paths": resolved_paths, "commands": executed}

        return self._invoke(tool_name="format_code", action_category="write", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"paths": paths}, paths=paths)

