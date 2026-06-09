from __future__ import annotations

import base64
import difflib
import fnmatch
import hashlib
import mimetypes
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import BaseToolset, ToolPayload
from .common import PathSafetyError, ValidationError, sanitize_text
from .path_manager import PathManager
from .permissions import PermissionProfile


@dataclass(slots=True)
class DiffHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[tuple[str, str]]


@dataclass(slots=True)
class ParsedFileDiff:
    old_path: str
    new_path: str
    hunks: list[DiffHunk]


def _normalize_diff_path(path_text: str) -> str:
    value = path_text.strip().split("\t", 1)[0]
    if value.startswith("a/") or value.startswith("b/"):
        value = value[2:]
    return value


def _parse_unified_diff(diff_text: str) -> list[ParsedFileDiff]:
    files: list[ParsedFileDiff] = []
    lines = diff_text.splitlines(keepends=True)
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.startswith("--- "):
            index += 1
            continue
        old_path = _normalize_diff_path(line[4:])
        index += 1
        if index >= len(lines) or not lines[index].startswith("+++ "):
            raise ValidationError("Unified diff is missing +++ header")
        new_path = _normalize_diff_path(lines[index][4:])
        index += 1
        hunks: list[DiffHunk] = []
        while index < len(lines) and not lines[index].startswith("--- "):
            current = lines[index]
            if not current.startswith("@@ "):
                index += 1
                continue
            header = current.strip()
            try:
                _, old_part, new_part, *_ = header.split(" ")
                old_start_text, old_count_text = old_part[1:].split(",") if "," in old_part else (old_part[1:], "1")
                new_start_text, new_count_text = new_part[1:].split(",") if "," in new_part else (new_part[1:], "1")
                old_start, old_count = int(old_start_text), int(old_count_text)
                new_start, new_count = int(new_start_text), int(new_count_text)
            except Exception as exc:
                raise ValidationError("Invalid unified diff hunk header", {"header": header}) from exc
            index += 1
            hunk_lines: list[tuple[str, str]] = []
            while index < len(lines):
                hunk_line = lines[index]
                if hunk_line.startswith("@@ ") or hunk_line.startswith("--- "):
                    break
                if hunk_line.startswith("\\ No newline at end of file"):
                    index += 1
                    continue
                prefix = hunk_line[:1]
                if prefix not in {" ", "+", "-"}:
                    raise ValidationError("Invalid unified diff line", {"line": hunk_line})
                hunk_lines.append((prefix, hunk_line[1:]))
                index += 1
            hunks.append(DiffHunk(old_start, old_count, new_start, new_count, hunk_lines))
        files.append(ParsedFileDiff(old_path=old_path, new_path=new_path, hunks=hunks))
    if not files:
        raise ValidationError("No file changes found in unified diff")
    return files


def _apply_hunks(original_text: str, hunks: list[DiffHunk]) -> str:
    original_lines = original_text.splitlines(keepends=True)
    result: list[str] = []
    cursor = 0
    for hunk in hunks:
        start = max(hunk.old_start - 1, 0)
        if start < cursor:
            raise ValidationError("Overlapping hunks are not supported")
        result.extend(original_lines[cursor:start])
        cursor = start
        for prefix, text in hunk.lines:
            if prefix == " ":
                if cursor >= len(original_lines) or original_lines[cursor] != text:
                    raise ValidationError("Unified diff context mismatch", {"expected": text, "actual": original_lines[cursor] if cursor < len(original_lines) else None})
                result.append(original_lines[cursor])
                cursor += 1
            elif prefix == "-":
                if cursor >= len(original_lines) or original_lines[cursor] != text:
                    raise ValidationError("Unified diff delete mismatch", {"expected": text, "actual": original_lines[cursor] if cursor < len(original_lines) else None})
                cursor += 1
            elif prefix == "+":
                result.append(text)
        # Count validation is intentionally relaxed; content matching is stricter.
    result.extend(original_lines[cursor:])
    return "".join(result)


class FileTools(BaseToolset):
    def __init__(self, *, path_manager: PathManager, **kwargs: Any):
        super().__init__(**kwargs)
        self.path_manager = path_manager

    def _list_entries(self, root: Path, recursive: bool, pattern: str) -> list[dict[str, Any]]:
        iterator = root.rglob(pattern) if recursive else root.glob(pattern)
        entries = []
        for item in iterator:
            resolved = item.resolve(strict=False)
            self.path_manager._check_allowed(resolved)
            stat = item.stat()
            entries.append(
                {
                    "path": str(item),
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "size": stat.st_size,
                    "modified_at": stat.st_mtime,
                }
            )
        return sorted(entries, key=lambda entry: entry["path"])

    def list_files(self, root_path: str | None = None, recursive: bool = False, pattern: str = "*") -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            root = self.path_manager.resolve_root(root_path)
            return {"root": str(root), "entries": self._list_entries(root, recursive, pattern)}

        return self._invoke(tool_name="list_files", action_category="read", operation=operation, args={"root_path": root_path, "recursive": recursive, "pattern": pattern}, paths=[root_path] if root_path else None)

    def list_tree(self, root_path: str | None = None, max_depth: int = 4) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            root = self.path_manager.resolve_root(root_path)
            entries: list[dict[str, Any]] = []
            for current_root, dirs, files in os.walk(root):
                current_path = Path(current_root)
                depth = len(current_path.relative_to(root).parts)
                if depth > max_depth:
                    dirs[:] = []
                    continue
                entries.append({"path": str(current_path), "depth": depth, "type": "directory"})
                for filename in sorted(files):
                    entries.append({"path": str(current_path / filename), "depth": depth + 1, "type": "file"})
            return {"root": str(root), "entries": entries}

        return self._invoke(tool_name="list_tree", action_category="read", operation=operation, args={"root_path": root_path, "max_depth": max_depth}, paths=[root_path] if root_path else None)

    def read_file(self, path: str, start_line: int | None = None, end_line: int | None = None, max_bytes: int | None = None) -> dict[str, Any]:
        def operation() -> ToolPayload:
            target = self.path_manager.resolve_path(path)
            content = target.read_text(encoding="utf-8", errors="replace")
            if start_line is not None or end_line is not None:
                lines = content.splitlines()
                start = max((start_line or 1) - 1, 0)
                end = end_line or len(lines)
                content = "\n".join(lines[start:end])
            limit = max_bytes or self.settings.max_read_bytes
            content, truncated = sanitize_text(content, limit)
            return ToolPayload({"path": str(target), "content": content}, truncated=truncated)

        return self._invoke(tool_name="read_file", action_category="read", operation=operation, args={"path": path, "start_line": start_line, "end_line": end_line, "max_bytes": max_bytes}, paths=[path])

    def read_files(self, paths: list[str], max_bytes_each: int | None = None) -> dict[str, Any]:
        def operation() -> ToolPayload:
            items = []
            any_truncated = False
            for raw_path in paths:
                target = self.path_manager.resolve_path(raw_path)
                content = target.read_text(encoding="utf-8", errors="replace")
                content, truncated = sanitize_text(content, max_bytes_each or self.settings.max_read_bytes)
                any_truncated = any_truncated or truncated
                items.append({"path": str(target), "content": content})
            return ToolPayload({"files": items}, truncated=any_truncated)

        return self._invoke(tool_name="read_files", action_category="read", operation=operation, args={"paths": paths, "max_bytes_each": max_bytes_each}, paths=paths)

    def read_binary_metadata(self, path: str, include_base64_preview: bool = False, preview_bytes: int = 128) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path)
            data = target.read_bytes()
            mime, _ = mimetypes.guess_type(target.name)
            result = {
                "path": str(target),
                "size": len(data),
                "mime_type": mime or "application/octet-stream",
            }
            if include_base64_preview:
                result["base64_preview"] = base64.b64encode(data[:preview_bytes]).decode("ascii")
            return result

        return self._invoke(tool_name="read_binary_metadata", action_category="read", operation=operation, args={"path": path, "include_base64_preview": include_base64_preview, "preview_bytes": preview_bytes}, paths=[path])

    def get_file_info(self, path: str) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path)
            stat = target.stat()
            return {
                "path": str(target),
                "is_dir": target.is_dir(),
                "size": stat.st_size,
                "modified_at": stat.st_mtime,
                "created_at": getattr(stat, "st_ctime", None),
                "suffix": target.suffix,
            }

        return self._invoke(tool_name="get_file_info", action_category="read", operation=operation, args={"path": path}, paths=[path])

    def create_file(self, path: str, content: str = "", token: str | None = None, confirm: bool = False) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path, allow_missing=True)
            if target.exists():
                raise ValidationError("File already exists; use write_file with FULL_CONTROL to overwrite", {"path": str(target)})
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return {"path": str(target), "bytes_written": len(content.encode("utf-8"))}

        return self._invoke(tool_name="create_file", action_category="write", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, confirm=confirm, args={"path": path}, paths=[path])

    def write_file(self, path: str, content: str, token: str | None = None, confirm: bool = False) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path, allow_missing=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return {"path": str(target), "bytes_written": len(content.encode("utf-8"))}

        return self._invoke(tool_name="write_file", action_category="write", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, confirm=confirm, destructive=True, args={"path": path}, paths=[path])

    def append_file(self, path: str, content: str, token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path, allow_missing=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as handle:
                handle.write(content)
            return {"path": str(target), "bytes_appended": len(content.encode("utf-8"))}

        return self._invoke(tool_name="append_file", action_category="write", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"path": path}, paths=[path])

    def patch_file(self, path: str, search_text: str, replacement: str, token: str | None = None, expected_count: int | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path)
            content = target.read_text(encoding="utf-8")
            count = content.count(search_text)
            if count == 0:
                raise ValidationError("search_text was not found", {"path": str(target)})
            if expected_count is not None and count != expected_count:
                raise ValidationError("search_text match count did not match expected_count", {"actual": count, "expected": expected_count})
            updated = content.replace(search_text, replacement)
            backup_path = target.with_suffix(target.suffix + ".bak")
            shutil.copy2(target, backup_path)
            target.write_text(updated, encoding="utf-8")
            return {"path": str(target), "replacements": count, "backup_path": str(backup_path)}

        return self._invoke(tool_name="patch_file", action_category="write", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"path": path, "expected_count": expected_count}, paths=[path])

    def replace_text(self, path: str, search_text: str, replacement: str, token: str | None = None, count: int = -1) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path)
            content = target.read_text(encoding="utf-8")
            if search_text not in content:
                raise ValidationError("search_text was not found", {"path": str(target)})
            updated = content.replace(search_text, replacement, count)
            target.write_text(updated, encoding="utf-8")
            replacements = content.count(search_text) if count < 0 else min(content.count(search_text), count)
            return {"path": str(target), "replacements": replacements}

        return self._invoke(tool_name="replace_text", action_category="write", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"path": path, "count": count}, paths=[path])

    def copy_path(self, source_path: str, destination_path: str, token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            source = self.path_manager.resolve_path(source_path)
            destination = self.path_manager.resolve_path(destination_path, allow_missing=True)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(source, destination)
            return {"source": str(source), "destination": str(destination)}

        return self._invoke(tool_name="copy_path", action_category="write", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"source_path": source_path, "destination_path": destination_path}, paths=[source_path, destination_path])

    def move_path(self, source_path: str, destination_path: str, token: str | None = None, confirm: bool = False) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            source = self.path_manager.resolve_path(source_path)
            destination = self.path_manager.resolve_path(destination_path, allow_missing=True)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            return {"source": str(source), "destination": str(destination)}

        return self._invoke(tool_name="move_path", action_category="write", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, confirm=confirm, args={"source_path": source_path, "destination_path": destination_path}, paths=[source_path, destination_path])

    def rename_path(self, path: str, new_name: str, token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            source = self.path_manager.resolve_path(path)
            destination = self.path_manager.resolve_path(str(source.parent / new_name), allow_missing=True)
            source.rename(destination)
            return {"source": str(source), "destination": str(destination)}

        return self._invoke(tool_name="rename_path", action_category="write", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"path": path, "new_name": new_name}, paths=[path])

    def delete_path(self, path: str, token: str | None = None, confirm: bool = False, recursive: bool = False) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path)
            if target.is_dir():
                if recursive:
                    shutil.rmtree(target)
                else:
                    target.rmdir()
            else:
                target.unlink()
            return {"path": str(target), "deleted": True}

        return self._invoke(tool_name="delete_path", action_category="write", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, confirm=confirm, destructive=True, args={"path": path, "recursive": recursive}, paths=[path])

    def create_directory(self, path: str, token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path, allow_missing=True)
            target.mkdir(parents=True, exist_ok=True)
            return {"path": str(target), "created": True}

        return self._invoke(tool_name="create_directory", action_category="write", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"path": path}, paths=[path])

    def calculate_hash(self, path: str, algorithm: str = "sha256") -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path)
            try:
                hasher = hashlib.new(algorithm)
            except ValueError as exc:
                raise ValidationError("Unsupported hash algorithm", {"algorithm": algorithm}) from exc
            with target.open("rb") as handle:
                for chunk in iter(lambda: handle.read(8192), b""):
                    hasher.update(chunk)
            return {"path": str(target), "algorithm": algorithm, "hash": hasher.hexdigest()}

        return self._invoke(tool_name="calculate_hash", action_category="read", operation=operation, args={"path": path, "algorithm": algorithm}, paths=[path])

    def apply_unified_diff(self, diff_text: str, token: str | None = None, dry_run: bool = False, validate: bool = True) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            parsed_files = _parse_unified_diff(diff_text)
            changed_files: list[str] = []
            for file_diff in parsed_files:
                if file_diff.old_path == "/dev/null":
                    raise ValidationError("Creating files from unified diff is not supported by this implementation")
                target = self.path_manager.resolve_path(file_diff.new_path or file_diff.old_path)
                original = target.read_text(encoding="utf-8", errors="replace")
                updated = _apply_hunks(original, file_diff.hunks)
                changed_files.append(str(target))
                if not dry_run:
                    backup_path = target.with_suffix(target.suffix + ".bak")
                    shutil.copy2(target, backup_path)
                    target.write_text(updated, encoding="utf-8")
            return {"changed_files": changed_files, "dry_run": dry_run, "validated": validate}

        return self._invoke(tool_name="apply_unified_diff", action_category="write", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"dry_run": dry_run, "validate": validate})

    def multi_file_patch(self, patches: list[dict[str, Any]], token: str | None = None, dry_run: bool = False) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            backups: dict[Path, str] = {}
            changed_files: list[str] = []
            try:
                for patch in patches:
                    if "unified_diff" in patch:
                        for file_diff in _parse_unified_diff(patch["unified_diff"]):
                            target = self.path_manager.resolve_path(file_diff.new_path or file_diff.old_path)
                            original = backups.setdefault(target, target.read_text(encoding="utf-8", errors="replace"))
                            current_text = target.read_text(encoding="utf-8", errors="replace") if str(target) in changed_files else original
                            updated = _apply_hunks(current_text, file_diff.hunks)
                            if not dry_run:
                                target.write_text(updated, encoding="utf-8")
                            changed_files.append(str(target))
                    else:
                        target = self.path_manager.resolve_path(patch["path"])
                        content = target.read_text(encoding="utf-8", errors="replace")
                        if patch["search_text"] not in content:
                            raise ValidationError("search_text was not found", {"path": str(target)})
                        if target not in backups:
                            backups[target] = content
                        updated = content.replace(patch["search_text"], patch["replacement"])
                        if not dry_run:
                            target.write_text(updated, encoding="utf-8")
                        changed_files.append(str(target))
                return {"changed_files": sorted(set(changed_files)), "rolled_back": False, "dry_run": dry_run}
            except Exception:
                if not dry_run:
                    for target, original in backups.items():
                        target.write_text(original, encoding="utf-8")
                raise

        return self._invoke(tool_name="multi_file_patch", action_category="write", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"patch_count": len(patches)})
