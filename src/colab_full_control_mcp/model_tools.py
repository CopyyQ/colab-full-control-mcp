from __future__ import annotations

import csv
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from .base import BaseToolset
from .common import ExecutionError, ValidationError, current_env_subset
from .job_manager import JobManager
from .path_manager import PathManager
from .permissions import PermissionProfile
from .runtime_tools import RuntimeTools


class ModelTools(BaseToolset):
    CHECKPOINT_PATTERNS = ["*.pt", "*.pth", "*.ckpt", "*.bin", "*.safetensors"]

    def __init__(self, *, path_manager: PathManager, job_manager: JobManager, runtime_tools: RuntimeTools, **kwargs: Any):
        super().__init__(**kwargs)
        self.path_manager = path_manager
        self.job_manager = job_manager
        self.runtime_tools = runtime_tools

    def _args_to_list(self, arguments: dict[str, Any] | list[str] | None) -> list[str]:
        if arguments is None:
            return []
        if isinstance(arguments, list):
            return [str(item) for item in arguments]
        parts: list[str] = []
        for key, value in arguments.items():
            flag = key if key.startswith("-") else f"--{key.replace('_', '-')}"
            if isinstance(value, bool):
                if value:
                    parts.append(flag)
            elif isinstance(value, list):
                for item in value:
                    parts.extend([flag, str(item)])
            elif value is not None:
                parts.extend([flag, str(value)])
        return parts

    def execute_project_task(
        self,
        task_type: str,
        project_path: str,
        entrypoint: str,
        arguments: dict[str, Any] | list[str] | None = None,
        environment: dict[str, str] | None = None,
        background: bool = True,
        timeout_seconds: int = 3600,
        log_path: str | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            project = self.path_manager.resolve_root(project_path)
            args = self._args_to_list(arguments)
            env = current_env_subset(environment or {})
            if task_type in {"python", "train", "validate", "inference", "benchmark", "export"}:
                target = self.path_manager.resolve_path(str(project / entrypoint) if not Path(entrypoint).is_absolute() else entrypoint)
                command = [sys.executable, str(target), *args]
            elif task_type == "test":
                command = [sys.executable, "-m", "pytest", *args]
            elif task_type == "git":
                command = ["git", entrypoint, *args]
            elif task_type == "custom":
                command = [entrypoint, *args]
            elif task_type == "notebook":
                notebook = self.path_manager.resolve_path(str(project / entrypoint) if not Path(entrypoint).is_absolute() else entrypoint)
                command = [sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute", str(notebook)]
            else:
                raise ValidationError("Unsupported task_type", {"task_type": task_type})
            if background:
                return self.job_manager.start_job(command=command, cwd=str(project), env=env, kind=task_type, log_path=log_path)
            import subprocess

            result = subprocess.run(command, cwd=str(project), env=env, capture_output=True, text=True, timeout=timeout_seconds, check=False)
            return {"command": command, "cwd": str(project), "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}

        return self._invoke(tool_name="execute_project_task", action_category="execute", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"task_type": task_type, "project_path": project_path, "entrypoint": entrypoint, "background": background, "timeout_seconds": timeout_seconds, "log_path": log_path}, paths=[project_path, entrypoint])

    def start_job(self, command: list[str], working_directory: str, token: str | None = None, environment: dict[str, str] | None = None, log_path: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            cwd = str(self.path_manager.resolve_root(working_directory))
            return self.job_manager.start_job(command=command, cwd=cwd, env=current_env_subset(environment or {}), kind="generic", log_path=log_path)

        return self._invoke(tool_name="start_job", action_category="execute", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"command": command, "working_directory": working_directory, "log_path": log_path}, paths=[working_directory])

    def start_python_job(self, script_path: str, working_directory: str | None = None, arguments: dict[str, Any] | list[str] | None = None, environment: dict[str, str] | None = None, log_path: str | None = None, token: str | None = None) -> dict[str, Any]:
        project = working_directory or str(self.path_manager.resolve_path(script_path).parent)
        return self.execute_project_task("python", project, script_path, arguments=arguments, environment=environment, background=True, log_path=log_path, token=token)

    def start_training_job(self, project_path: str, script_path: str, arguments: dict[str, Any] | list[str] | None = None, environment: dict[str, str] | None = None, log_path: str | None = None, token: str | None = None) -> dict[str, Any]:
        return self.execute_project_task("train", project_path, script_path, arguments=arguments, environment=environment, background=True, log_path=log_path, token=token)

    def resume_training_job(self, project_path: str, script_path: str, arguments: dict[str, Any] | list[str] | None = None, environment: dict[str, str] | None = None, log_path: str | None = None, token: str | None = None) -> dict[str, Any]:
        return self.start_training_job(project_path, script_path, arguments=arguments, environment=environment, log_path=log_path, token=token)

    def start_notebook_job(self, project_path: str, notebook_path: str, token: str | None = None, log_path: str | None = None) -> dict[str, Any]:
        return self.execute_project_task("notebook", project_path, notebook_path, background=True, log_path=log_path, token=token)

    def run_validation_job(self, project_path: str, script_path: str, arguments: dict[str, Any] | list[str] | None = None, environment: dict[str, str] | None = None, log_path: str | None = None, token: str | None = None) -> dict[str, Any]:
        return self.execute_project_task("validate", project_path, script_path, arguments=arguments, environment=environment, background=True, log_path=log_path, token=token)

    def run_inference_job(self, project_path: str, script_path: str, arguments: dict[str, Any] | list[str] | None = None, environment: dict[str, str] | None = None, log_path: str | None = None, token: str | None = None) -> dict[str, Any]:
        return self.execute_project_task("inference", project_path, script_path, arguments=arguments, environment=environment, background=True, log_path=log_path, token=token)

    def run_benchmark_job(self, project_path: str, script_path: str, arguments: dict[str, Any] | list[str] | None = None, environment: dict[str, str] | None = None, log_path: str | None = None, token: str | None = None) -> dict[str, Any]:
        return self.execute_project_task("benchmark", project_path, script_path, arguments=arguments, environment=environment, background=True, log_path=log_path, token=token)

    def export_model_job(self, project_path: str, script_path: str, arguments: dict[str, Any] | list[str] | None = None, environment: dict[str, str] | None = None, log_path: str | None = None, token: str | None = None) -> dict[str, Any]:
        return self.execute_project_task("export", project_path, script_path, arguments=arguments, environment=environment, background=True, log_path=log_path, token=token)

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        return self._invoke(tool_name="get_job_status", action_category="read", operation=lambda: self.job_manager.get_job_status(job_id), args={"job_id": job_id})

    def get_job_logs(self, job_id: str, tail_chars: int | None = None) -> dict[str, Any]:
        return self._invoke(tool_name="get_job_logs", action_category="read", operation=lambda: self.job_manager.get_job_logs(job_id, tail_chars=tail_chars), args={"job_id": job_id, "tail_chars": tail_chars})

    def stream_job_logs(self, job_id: str, offset: int = 0, limit: int = 4000) -> dict[str, Any]:
        return self._invoke(tool_name="stream_job_logs", action_category="read", operation=lambda: self.job_manager.stream_job_logs(job_id, offset=offset, limit=limit), args={"job_id": job_id, "offset": offset, "limit": limit})

    def list_jobs(self) -> dict[str, Any]:
        return self._invoke(tool_name="list_jobs", action_category="read", operation=lambda: {"jobs": self.job_manager.list_jobs()})

    def stop_job(self, job_id: str, token: str | None = None, confirm: bool = False) -> dict[str, Any]:
        return self._invoke(tool_name="stop_job", action_category="execute", operation=lambda: self.job_manager.stop_job(job_id), min_profile=PermissionProfile.FULL_CONTROL, token=token, confirm=confirm, destructive=True, args={"job_id": job_id})

    def restart_job(self, job_id: str, token: str | None = None) -> dict[str, Any]:
        return self._invoke(tool_name="restart_job", action_category="execute", operation=lambda: self.job_manager.restart_job(job_id), min_profile=PermissionProfile.DEVELOPER, token=token, args={"job_id": job_id})

    def wait_for_job(self, job_id: str, timeout_seconds: float | None = None) -> dict[str, Any]:
        return self._invoke(tool_name="wait_for_job", action_category="read", operation=lambda: self.job_manager.wait_for_job(job_id, timeout_seconds=timeout_seconds), args={"job_id": job_id, "timeout_seconds": timeout_seconds})

    def delete_job_record(self, job_id: str, token: str | None = None, confirm: bool = False) -> dict[str, Any]:
        return self._invoke(tool_name="delete_job_record", action_category="execute", operation=lambda: self.job_manager.delete_job_record(job_id), min_profile=PermissionProfile.FULL_CONTROL, token=token, confirm=confirm, destructive=True, args={"job_id": job_id})

    def get_training_progress(self, job_id: str) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            logs = self.job_manager.get_job_logs(job_id)["content"]
            epoch_matches = re.findall(r"epoch[^0-9]*(\d+)", logs, re.IGNORECASE)
            percent_matches = re.findall(r"(\d{1,3}(?:\.\d+)?)%", logs)
            return {"job_id": job_id, "epochs_seen": [int(item) for item in epoch_matches], "percent_markers": [float(item) for item in percent_matches], "log_tail": logs[-2000:]}

        return self._invoke(tool_name="get_training_progress", action_category="read", operation=operation, args={"job_id": job_id})

    def read_metrics(self, path: str) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path)
            if target.suffix == ".json":
                return {"path": str(target), "metrics": json.loads(target.read_text(encoding="utf-8"))}
            if target.suffix == ".csv":
                with target.open("r", encoding="utf-8", newline="") as handle:
                    reader = csv.DictReader(handle)
                    return {"path": str(target), "metrics": list(reader)}
            raise ValidationError("Unsupported metrics file format", {"path": str(target)})

        return self._invoke(tool_name="read_metrics", action_category="read", operation=operation, args={"path": path}, paths=[path])

    def compare_metrics(self, metrics_a: dict[str, Any], metrics_b: dict[str, Any]) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            keys = sorted(set(metrics_a) | set(metrics_b))
            deltas = {}
            for key in keys:
                a_val = metrics_a.get(key)
                b_val = metrics_b.get(key)
                if isinstance(a_val, (int, float)) and isinstance(b_val, (int, float)):
                    deltas[key] = {"a": a_val, "b": b_val, "delta": b_val - a_val}
                else:
                    deltas[key] = {"a": a_val, "b": b_val}
            return {"comparison": deltas}

        return self._invoke(tool_name="compare_metrics", action_category="read", operation=operation)

    def list_checkpoints(self, root_path: str) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            root = self.path_manager.resolve_root(root_path)
            entries = []
            for pattern in self.CHECKPOINT_PATTERNS:
                for file_path in root.rglob(pattern):
                    entries.append({"path": str(file_path), "size": file_path.stat().st_size, "modified_at": file_path.stat().st_mtime})
            return {"root": str(root), "checkpoints": sorted(entries, key=lambda item: item["path"])}

        return self._invoke(tool_name="list_checkpoints", action_category="read", operation=operation, args={"root_path": root_path})

    def find_best_checkpoint(self, metadata_path: str, metric_name: str, mode: str = "max") -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(metadata_path)
            content = json.loads(target.read_text(encoding="utf-8"))
            candidates = content if isinstance(content, list) else content.get("checkpoints", [])
            if mode not in {"max", "min"}:
                raise ValidationError("mode must be 'max' or 'min'")
            if not candidates:
                raise ValidationError("No checkpoint metadata found")
            best = max(candidates, key=lambda item: item[metric_name]) if mode == "max" else min(candidates, key=lambda item: item[metric_name])
            return {"metadata_path": str(target), "metric_name": metric_name, "mode": mode, "best_checkpoint": best}

        return self._invoke(tool_name="find_best_checkpoint", action_category="read", operation=operation, args={"metadata_path": metadata_path, "metric_name": metric_name, "mode": mode}, paths=[metadata_path])

    def get_checkpoint_info(self, path: str) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path)
            stat = target.stat()
            return {"path": str(target), "size": stat.st_size, "modified_at": stat.st_mtime}

        return self._invoke(tool_name="get_checkpoint_info", action_category="read", operation=operation, args={"path": path}, paths=[path])

    def copy_checkpoint(self, source_path: str, destination_path: str, token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            source = self.path_manager.resolve_path(source_path)
            destination = self.path_manager.resolve_path(destination_path, allow_missing=True)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            return {"source": str(source), "destination": str(destination)}

        return self._invoke(tool_name="copy_checkpoint", action_category="write", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, args={"source_path": source_path, "destination_path": destination_path}, paths=[source_path, destination_path])

    def delete_checkpoint(self, path: str, token: str | None = None, confirm: bool = False) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path)
            target.unlink()
            return {"path": str(target), "deleted": True}

        return self._invoke(tool_name="delete_checkpoint", action_category="write", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, confirm=confirm, destructive=True, args={"path": path}, paths=[path])

    def export_checkpoint(self, source_path: str, destination_path: str, token: str | None = None, confirm: bool = False) -> dict[str, Any]:
        return self.copy_checkpoint(source_path, destination_path, token=token)

    def inspect_model(self, path: str) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = self.path_manager.resolve_path(path)
            info = {"path": str(target), "size": target.stat().st_size, "suffix": target.suffix}
            if importlib.util.find_spec("torch") is not None:  # type: ignore[name-defined]
                import torch

                try:
                    data = torch.load(target, map_location="cpu")
                    if isinstance(data, dict):
                        info["top_level_keys"] = list(data.keys())[:20]
                except Exception:
                    pass
            return info

        import importlib.util

        return self._invoke(tool_name="inspect_model", action_category="read", operation=operation, args={"path": path}, paths=[path])

    def count_parameters(self, path: str) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            import importlib.util

            if importlib.util.find_spec("torch") is None:
                raise ExecutionError("torch is not installed")
            import torch

            target = self.path_manager.resolve_path(path)
            data = torch.load(target, map_location="cpu")
            if isinstance(data, dict):
                tensor_like = [value for value in data.values() if hasattr(value, "numel")]
                total = sum(int(value.numel()) for value in tensor_like)
                return {"path": str(target), "parameter_count": total}
            raise ValidationError("Unsupported checkpoint structure for parameter counting")

        return self._invoke(tool_name="count_parameters", action_category="read", operation=operation, args={"path": path}, paths=[path])

    def measure_gpu_memory(self) -> dict[str, Any]:
        return self.runtime_tools.get_gpu_status()
