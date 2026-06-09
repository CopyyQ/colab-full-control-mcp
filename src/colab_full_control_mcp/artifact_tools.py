from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Any

import yaml
from PIL import Image

from .base import BaseToolset
from .path_manager import PathManager
from .permissions import PermissionProfile


class ArtifactTools(BaseToolset):
    def __init__(self, *, path_manager: PathManager, **kwargs: Any):
        super().__init__(**kwargs)
        self.path_manager = path_manager

    def list_artifacts(self, root_path: str, patterns: list[str] | None = None, max_results: int = 200) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            root = self.path_manager.resolve_root(root_path)
            suffixes = patterns or ["*.png", "*.jpg", "*.jpeg", "*.csv", "*.json", "*.yaml", "*.yml", "*.log", "*.pt", "*.pth", "*.ckpt", "*.onnx"]
            entries = []
            for file_path in root.rglob("*"):
                if not file_path.is_file():
                    continue
                if any(file_path.match(pattern) for pattern in suffixes):
                    entries.append({"path": str(file_path), "size": file_path.stat().st_size})
                if len(entries) >= max_results:
                    break
            return {"root": str(root), "entries": entries}

        return self._invoke(tool_name="list_artifacts", action_category="read", operation=operation, args={"root_path": root_path, "patterns": patterns, "max_results": max_results})

    def get_artifact_info(self, path: str) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path)
            return {"path": str(target), "size": target.stat().st_size, "suffix": target.suffix}

        return self._invoke(tool_name="get_artifact_info", action_category="read", operation=operation, args={"path": path}, paths=[path])

    def read_csv(self, path: str, limit: int = 100) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path)
            with target.open("r", encoding="utf-8", errors="replace", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = []
                for index, row in enumerate(reader):
                    rows.append(row)
                    if index + 1 >= limit:
                        break
            return {"path": str(target), "rows": rows, "row_count": len(rows)}

        return self._invoke(tool_name="read_csv", action_category="read", operation=operation, args={"path": path, "limit": limit}, paths=[path])

    def read_json(self, path: str) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path)
            return {"path": str(target), "content": json.loads(target.read_text(encoding="utf-8"))}

        return self._invoke(tool_name="read_json", action_category="read", operation=operation, args={"path": path}, paths=[path])

    def read_yaml(self, path: str) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path)
            return {"path": str(target), "content": yaml.safe_load(target.read_text(encoding="utf-8"))}

        return self._invoke(tool_name="read_yaml", action_category="read", operation=operation, args={"path": path}, paths=[path])

    def inspect_image(self, path: str) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path)
            with Image.open(target) as image:
                return {"path": str(target), "size": image.size, "mode": image.mode, "format": image.format, "info": dict(image.info)}

        return self._invoke(tool_name="inspect_image", action_category="read", operation=operation, args={"path": path}, paths=[path])

    def save_plot(
        self,
        output_path: str,
        x_values: list[float] | list[int],
        y_values: list[float] | list[int],
        title: str | None = None,
        xlabel: str | None = None,
        ylabel: str | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            if len(x_values) != len(y_values):
                raise ValueError("x_values and y_values must have the same length")
            try:
                import matplotlib.pyplot as plt
            except ImportError as exc:  # pragma: no cover - depends on environment
                raise RuntimeError("matplotlib is not installed") from exc
            destination = self.path_manager.resolve_path(output_path, allow_missing=True)
            destination.parent.mkdir(parents=True, exist_ok=True)
            plt.figure()
            plt.plot(x_values, y_values)
            if title:
                plt.title(title)
            if xlabel:
                plt.xlabel(xlabel)
            if ylabel:
                plt.ylabel(ylabel)
            plt.tight_layout()
            plt.savefig(destination)
            plt.close()
            return {"output_path": str(destination)}

        return self._invoke(tool_name="save_plot", action_category="write", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"output_path": output_path, "point_count": len(x_values)}, paths=[output_path])

    def create_archive(self, source_path: str, archive_path: str, token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            source = self.path_manager.resolve_path(source_path)
            destination = self.path_manager.resolve_path(archive_path, allow_missing=True)
            destination.parent.mkdir(parents=True, exist_ok=True)
            base_name = str(destination.with_suffix(""))
            archive = shutil.make_archive(base_name, "zip", root_dir=str(source))
            return {"source": str(source), "archive_path": archive}

        return self._invoke(tool_name="create_archive", action_category="write", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"source_path": source_path, "archive_path": archive_path}, paths=[source_path, archive_path])

    def extract_archive(self, archive_path: str, destination_path: str, token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            archive = self.path_manager.resolve_path(archive_path)
            destination = self.path_manager.resolve_path(destination_path, allow_missing=True)
            destination.mkdir(parents=True, exist_ok=True)
            shutil.unpack_archive(str(archive), str(destination))
            return {"archive_path": str(archive), "destination_path": str(destination)}

        return self._invoke(tool_name="extract_archive", action_category="write", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"archive_path": archive_path, "destination_path": destination_path}, paths=[archive_path, destination_path])
