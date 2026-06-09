from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .base import BaseToolset
from .path_manager import PathManager
from .permissions import PermissionProfile


class DriveTools(BaseToolset):
    def __init__(self, *, path_manager: PathManager, **kwargs: Any):
        super().__init__(**kwargs)
        self.path_manager = path_manager

    @property
    def drive_root(self) -> Path:
        for root in self.path_manager.allowed_roots:
            if "MyDrive" in str(root):
                return root
        return self.path_manager.primary_root

    def is_drive_mounted(self) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            return {"drive_root": str(self.drive_root), "mounted": self.drive_root.exists()}

        return self._invoke(tool_name="is_drive_mounted", action_category="read", operation=operation)

    def mount_drive_status(self) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            mounted = self.drive_root.exists()
            message = "Drive appears mounted" if mounted else "Drive is not mounted. Use the setup notebook mount cell in Colab."
            return {"drive_root": str(self.drive_root), "mounted": mounted, "message": message}

        return self._invoke(tool_name="mount_drive_status", action_category="read", operation=operation)

    def list_drive_files(self, path: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.drive_root if path is None else self.path_manager.resolve_path(path)
            entries = [{"path": str(item), "is_dir": item.is_dir()} for item in sorted(target.iterdir())]
            return {"root": str(target), "entries": entries}

        return self._invoke(tool_name="list_drive_files", action_category="read", operation=operation, args={"path": path}, paths=[path] if path else None)

    def read_drive_file(self, path: str) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path)
            return {"path": str(target), "content": target.read_text(encoding="utf-8", errors="replace")}

        return self._invoke(tool_name="read_drive_file", action_category="read", operation=operation, args={"path": path}, paths=[path])

    def copy_to_drive(self, source_path: str, drive_path: str, token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            source = self.path_manager.resolve_path(source_path)
            destination = self.path_manager.resolve_path(drive_path, allow_missing=True)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(source, destination)
            return {"source": str(source), "destination": str(destination)}

        return self._invoke(tool_name="copy_to_drive", action_category="write", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, args={"source_path": source_path, "drive_path": drive_path}, paths=[source_path, drive_path])

    def copy_from_drive(self, drive_path: str, destination_path: str, token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            source = self.path_manager.resolve_path(drive_path)
            destination = self.path_manager.resolve_path(destination_path, allow_missing=True)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(source, destination)
            return {"source": str(source), "destination": str(destination)}

        return self._invoke(tool_name="copy_from_drive", action_category="write", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, args={"drive_path": drive_path, "destination_path": destination_path}, paths=[drive_path, destination_path])

    def sync_project_to_drive(self, project_path: str, drive_path: str, token: str | None = None) -> dict[str, Any]:
        return self.copy_to_drive(project_path, drive_path, token=token)

    def sync_project_from_drive(self, drive_path: str, project_path: str, token: str | None = None) -> dict[str, Any]:
        return self.copy_from_drive(drive_path, project_path, token=token)

    def backup_project(self, project_path: str, backup_path: str, token: str | None = None) -> dict[str, Any]:
        return self.copy_to_drive(project_path, backup_path, token=token)

    def backup_checkpoints(self, checkpoint_path: str, backup_path: str, token: str | None = None) -> dict[str, Any]:
        return self.copy_to_drive(checkpoint_path, backup_path, token=token)

    def delete_drive_path(self, path: str, token: str | None = None, confirm: bool = False) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path)
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            return {"path": str(target), "deleted": True}

        return self._invoke(tool_name="delete_drive_path", action_category="write", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, confirm=confirm, destructive=True, args={"path": path}, paths=[path])

