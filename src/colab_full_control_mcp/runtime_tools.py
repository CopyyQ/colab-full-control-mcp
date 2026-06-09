from __future__ import annotations

import gc
import importlib.util
import os
import subprocess
from pathlib import Path
from typing import Any

import psutil

from .base import BaseToolset
from .job_manager import JobManager
from .permissions import PermissionProfile


class RuntimeTools(BaseToolset):
    def __init__(self, *, job_manager: JobManager, **kwargs: Any):
        super().__init__(**kwargs)
        self.job_manager = job_manager

    def get_cpu_status(self) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            return {"cpu_percent": psutil.cpu_percent(interval=0.1), "cpu_count": psutil.cpu_count(), "load_avg": os.getloadavg() if hasattr(os, "getloadavg") else None}

        return self._invoke(tool_name="get_cpu_status", action_category="read", operation=operation)

    def get_memory_status(self) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            memory = psutil.virtual_memory()
            return {"total": memory.total, "available": memory.available, "used": memory.used, "percent": memory.percent}

        return self._invoke(tool_name="get_memory_status", action_category="read", operation=operation)

    def get_disk_status(self, path: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target = Path(path or self.settings.allowed_roots[0]).expanduser()
            disk = psutil.disk_usage(str(target))
            return {"path": str(target), "total": disk.total, "used": disk.used, "free": disk.free, "percent": disk.percent}

        return self._invoke(tool_name="get_disk_status", action_category="read", operation=operation, args={"path": path})

    def get_network_status(self) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            counters = psutil.net_io_counters()
            return {"bytes_sent": counters.bytes_sent, "bytes_recv": counters.bytes_recv, "packets_sent": counters.packets_sent, "packets_recv": counters.packets_recv}

        return self._invoke(tool_name="get_network_status", action_category="read", operation=operation)

    def get_gpu_status(self) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            if shutil.which("nvidia-smi") is None:  # type: ignore[name-defined]
                return {"available": False}
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            gpus = []
            for line in result.stdout.splitlines():
                parts = [part.strip() for part in line.split(",")]
                if len(parts) == 4:
                    gpus.append({"name": parts[0], "memory_total_mb": parts[1], "memory_used_mb": parts[2], "utilization_gpu_percent": parts[3]})
            return {"available": bool(gpus), "gpus": gpus}

        import shutil

        return self._invoke(tool_name="get_gpu_status", action_category="read", operation=operation)

    def get_process_list(self) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            processes = []
            for proc in psutil.process_iter(["pid", "name", "status", "cmdline"]):
                info = proc.info
                cmdline = " ".join(info.get("cmdline") or [])
                redacted = "[REDACTED]" if any(term in cmdline.lower() for term in ["token", "secret", "password", "api_key"]) else cmdline
                processes.append({"pid": info["pid"], "name": info["name"], "status": info["status"], "cmdline": redacted})
            return {"processes": processes}

        return self._invoke(tool_name="get_process_list", action_category="read", operation=operation)

    def get_cuda_status(self) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            torch_spec = importlib.util.find_spec("torch")
            if torch_spec is None:
                return {"torch_available": False, "cuda_available": False}
            import torch

            return {"torch_available": True, "cuda_available": torch.cuda.is_available(), "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0}

        return self._invoke(tool_name="get_cuda_status", action_category="read", operation=operation)

    def get_pytorch_status(self) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            torch_spec = importlib.util.find_spec("torch")
            if torch_spec is None:
                return {"available": False}
            import torch

            return {"available": True, "version": torch.__version__, "cuda_available": torch.cuda.is_available()}

        return self._invoke(tool_name="get_pytorch_status", action_category="read", operation=operation)

    def get_colab_status(self) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            return {"in_colab": importlib.util.find_spec("google.colab") is not None, "content_exists": Path("/content").exists()}

        return self._invoke(tool_name="get_colab_status", action_category="read", operation=operation)

    def get_runtime_status(self) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            return {
                "cpu": self.get_cpu_status()["data"],
                "memory": self.get_memory_status()["data"],
                "disk": self.get_disk_status()["data"],
                "gpu": self.get_gpu_status()["data"],
                "colab": self.get_colab_status()["data"],
            }

        return self._invoke(tool_name="get_runtime_status", action_category="read", operation=operation)

    def clear_cuda_cache(self, token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            if importlib.util.find_spec("torch") is None:
                return {"cleared": False, "reason": "torch is not installed"}
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                return {"cleared": True}
            return {"cleared": False, "reason": "CUDA is not available"}

        return self._invoke(tool_name="clear_cuda_cache", action_category="execute", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token)

    def garbage_collect(self, token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            return {"collected": gc.collect()}

        return self._invoke(tool_name="garbage_collect", action_category="execute", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token)

    def terminate_managed_process(self, job_id: str, token: str | None = None, confirm: bool = False) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            return self.job_manager.stop_job(job_id)

        return self._invoke(tool_name="terminate_managed_process", action_category="execute", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, confirm=confirm, destructive=True, args={"job_id": job_id})

    def restart_mcp_server(self, token: str | None = None, confirm: bool = False) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            return {
                "message": "Restart the server process from the controlling notebook or script. The current response channel may be interrupted by a real in-process restart.",
                "host": self.settings.host,
                "port": self.settings.port,
                "mount_path": self.settings.mount_path,
            }

        return self._invoke(tool_name="restart_mcp_server", action_category="execute", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, confirm=confirm, destructive=True)

