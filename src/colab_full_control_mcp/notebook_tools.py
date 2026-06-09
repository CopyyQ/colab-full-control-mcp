from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import nbformat
import psutil
from nbclient import NotebookClient

from .base import BaseToolset, ToolPayload
from .common import ExecutionError, ValidationError, ensure_directory
from .path_manager import PathManager
from .permissions import PermissionProfile


@dataclass(slots=True)
class SessionRecord:
    session_id: str
    process: subprocess.Popen[str]
    working_directory: str
    creation_time: float
    last_activity: float
    execution_count: int
    log_path: str
    last_output: dict[str, Any]


class PythonSessionManager:
    def __init__(self, session_root: Path):
        self.session_root = ensure_directory(session_root.expanduser())
        self.sessions: dict[str, SessionRecord] = {}

    def _session_command(self) -> list[str]:
        worker_path = Path(__file__).with_name("session_worker.py")
        return [sys.executable, "-u", str(worker_path)]

    def create_session(self, working_directory: str) -> dict[str, Any]:
        session_id = uuid.uuid4().hex
        log_path = self.session_root / f"{session_id}.session.log"
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        kwargs: dict[str, Any] = {"text": True, "stdin": subprocess.PIPE, "stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
        if os.name == "nt":
            kwargs["creationflags"] = creationflags
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(self._session_command(), cwd=working_directory, **kwargs)
        now = time.time()
        record = SessionRecord(
            session_id=session_id,
            process=process,
            working_directory=working_directory,
            creation_time=now,
            last_activity=now,
            execution_count=0,
            log_path=str(log_path),
            last_output={},
        )
        self.sessions[session_id] = record
        return self.get_status(session_id)

    def _get(self, session_id: str) -> SessionRecord:
        try:
            return self.sessions[session_id]
        except KeyError as exc:
            raise ExecutionError(f"Unknown session: {session_id}") from exc

    def _request(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = self._get(session_id)
        if record.process.stdin is None or record.process.stdout is None:
            raise ExecutionError("Session pipes are not available", {"session_id": session_id})
        record.process.stdin.write(json.dumps(payload, ensure_ascii=True) + "\n")
        record.process.stdin.flush()
        response_line = record.process.stdout.readline()
        if not response_line:
            stderr = ""
            if record.process.stderr is not None:
                stderr = record.process.stderr.read() or ""
            raise ExecutionError("Session did not return a response", {"stderr": stderr})
        response = json.loads(response_line)
        record.last_activity = time.time()
        record.last_output = response
        if not response.get("ok"):
            raise ExecutionError("Session execution failed", response.get("error", {}))
        return response

    def execute(self, session_id: str, code: str) -> dict[str, Any]:
        record = self._get(session_id)
        response = self._request(session_id, {"action": "execute", "code": code})
        record.execution_count += 1
        return response

    def list_variables(self, session_id: str) -> dict[str, Any]:
        return self._request(session_id, {"action": "list_vars"})

    def delete_variable(self, session_id: str, name: str) -> dict[str, Any]:
        return self._request(session_id, {"action": "delete_var", "name": name})

    def interrupt(self, session_id: str) -> dict[str, Any]:
        record = self._get(session_id)
        process = record.process
        if process.poll() is not None:
            raise ExecutionError("Session is not running", {"session_id": session_id})
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.send_signal(signal.SIGINT)
        return self.get_status(session_id)

    def close(self, session_id: str) -> dict[str, Any]:
        record = self._get(session_id)
        try:
            self._request(session_id, {"action": "close"})
        except ExecutionError:
            pass
        if record.process.poll() is None:
            record.process.terminate()
            try:
                record.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                record.process.kill()
        status = self.get_status(session_id)
        return {"session_id": session_id, "closed": True, "status": status["status"]}

    def restart(self, session_id: str) -> dict[str, Any]:
        record = self._get(session_id)
        cwd = record.working_directory
        self.close(session_id)
        self.sessions.pop(session_id, None)
        return self.create_session(cwd)

    def get_status(self, session_id: str) -> dict[str, Any]:
        record = self._get(session_id)
        status = "running" if record.process.poll() is None else "stopped"
        return {
            "session_id": session_id,
            "status": status,
            "creation_time": record.creation_time,
            "last_activity": record.last_activity,
            "working_directory": record.working_directory,
            "execution_count": record.execution_count,
            "log_path": record.log_path,
            "pid": record.process.pid,
        }

    def list_sessions(self) -> list[dict[str, Any]]:
        return [self.get_status(session_id) for session_id in sorted(self.sessions)]

    def get_output(self, session_id: str) -> dict[str, Any]:
        record = self._get(session_id)
        return {"session_id": session_id, "last_output": record.last_output}


class NotebookTools(BaseToolset):
    def __init__(self, *, path_manager: PathManager, session_manager: PythonSessionManager, **kwargs: Any):
        super().__init__(**kwargs)
        self.path_manager = path_manager
        self.session_manager = session_manager

    def _read_notebook(self, path: str) -> tuple[Path, nbformat.NotebookNode]:
        target = self.path_manager.resolve_path(path)
        return target, nbformat.read(target, as_version=4)

    def _write_notebook(self, target: Path, notebook: nbformat.NotebookNode) -> None:
        nbformat.write(notebook, target)

    def list_notebook_cells(self, path: str) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target, notebook = self._read_notebook(path)
            cells = [
                {
                    "index": index,
                    "cell_type": cell.cell_type,
                    "source_preview": cell.source.splitlines()[:3],
                }
                for index, cell in enumerate(notebook.cells)
            ]
            return {"path": str(target), "cells": cells}

        return self._invoke(tool_name="list_notebook_cells", action_category="read", operation=operation, args={"path": path}, paths=[path])

    def read_notebook(self, path: str, include_outputs: bool = False, max_cells: int = 200) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target, notebook = self._read_notebook(path)
            cells = []
            for index, cell in enumerate(notebook.cells[:max_cells]):
                entry = {"index": index, "cell_type": cell.cell_type, "source": cell.source}
                if include_outputs and cell.cell_type == "code":
                    entry["outputs"] = cell.get("outputs", [])
                cells.append(entry)
            return {"path": str(target), "metadata": notebook.metadata, "cells": cells, "cell_count": len(notebook.cells)}

        return self._invoke(tool_name="read_notebook", action_category="read", operation=operation, args={"path": path, "include_outputs": include_outputs, "max_cells": max_cells}, paths=[path])

    def read_notebook_cell(self, path: str, cell_index: int) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target, notebook = self._read_notebook(path)
            try:
                cell = notebook.cells[cell_index]
            except IndexError as exc:
                raise ValidationError("cell_index is out of range", {"cell_index": cell_index}) from exc
            return {"path": str(target), "index": cell_index, "cell": cell}

        return self._invoke(tool_name="read_notebook_cell", action_category="read", operation=operation, args={"path": path, "cell_index": cell_index}, paths=[path])

    def update_notebook_cell(self, path: str, cell_index: int, source: str, token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target, notebook = self._read_notebook(path)
            notebook.cells[cell_index].source = source
            self._write_notebook(target, notebook)
            return {"path": str(target), "index": cell_index, "updated": True}

        return self._invoke(tool_name="update_notebook_cell", action_category="write", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, args={"path": path, "cell_index": cell_index}, paths=[path])

    def insert_notebook_cell(self, path: str, cell_index: int, source: str, cell_type: str = "code", token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target, notebook = self._read_notebook(path)
            new_cell = nbformat.v4.new_code_cell(source) if cell_type == "code" else nbformat.v4.new_markdown_cell(source)
            notebook.cells.insert(cell_index, new_cell)
            self._write_notebook(target, notebook)
            return {"path": str(target), "index": cell_index, "inserted": True}

        return self._invoke(tool_name="insert_notebook_cell", action_category="write", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, args={"path": path, "cell_index": cell_index, "cell_type": cell_type}, paths=[path])

    def append_notebook_cell(self, path: str, source: str, cell_type: str = "code", token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target, notebook = self._read_notebook(path)
            new_cell = nbformat.v4.new_code_cell(source) if cell_type == "code" else nbformat.v4.new_markdown_cell(source)
            notebook.cells.append(new_cell)
            self._write_notebook(target, notebook)
            return {"path": str(target), "index": len(notebook.cells) - 1, "appended": True}

        return self._invoke(tool_name="append_notebook_cell", action_category="write", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, args={"path": path, "cell_type": cell_type}, paths=[path])

    def move_notebook_cell(self, path: str, source_index: int, destination_index: int, token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target, notebook = self._read_notebook(path)
            cell = notebook.cells.pop(source_index)
            notebook.cells.insert(destination_index, cell)
            self._write_notebook(target, notebook)
            return {"path": str(target), "source_index": source_index, "destination_index": destination_index}

        return self._invoke(tool_name="move_notebook_cell", action_category="write", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, args={"path": path, "source_index": source_index, "destination_index": destination_index}, paths=[path])

    def delete_notebook_cell(self, path: str, cell_index: int, token: str | None = None, confirm: bool = False) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target, notebook = self._read_notebook(path)
            notebook.cells.pop(cell_index)
            self._write_notebook(target, notebook)
            return {"path": str(target), "index": cell_index, "deleted": True}

        return self._invoke(tool_name="delete_notebook_cell", action_category="write", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, confirm=confirm, destructive=True, args={"path": path, "cell_index": cell_index}, paths=[path])

    def clear_notebook_outputs(self, path: str, token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target, notebook = self._read_notebook(path)
            for cell in notebook.cells:
                if cell.cell_type == "code":
                    cell.outputs = []
                    cell.execution_count = None
            self._write_notebook(target, notebook)
            return {"path": str(target), "cleared": True}

        return self._invoke(tool_name="clear_notebook_outputs", action_category="write", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, args={"path": path}, paths=[path])

    def set_notebook_metadata(self, path: str, metadata: dict[str, Any], token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target, notebook = self._read_notebook(path)
            notebook.metadata.update(metadata)
            self._write_notebook(target, notebook)
            return {"path": str(target), "metadata": notebook.metadata}

        return self._invoke(tool_name="set_notebook_metadata", action_category="write", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, args={"path": path, "metadata_keys": sorted(metadata)}, paths=[path])

    def run_notebook(self, path: str, token: str | None = None, working_directory: str | None = None, timeout: int = 600, output_path: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target, notebook = self._read_notebook(path)
            cwd = str(self.path_manager.resolve_root(working_directory or str(target.parent)))
            client = NotebookClient(notebook, timeout=timeout, kernel_name="python3")
            executed = client.execute(cwd=cwd)
            if output_path:
                destination = self.path_manager.resolve_path(output_path, allow_missing=True)
            else:
                destination = target.with_name(target.stem + ".executed.ipynb")
            self._write_notebook(destination, executed)
            return {"path": str(target), "output_path": str(destination), "executed": True}

        return self._invoke(tool_name="run_notebook", action_category="execute", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"path": path, "working_directory": working_directory, "timeout": timeout, "output_path": output_path}, paths=[path, output_path] if output_path else [path])

    def run_notebook_cell(self, path: str, cell_index: int, token: str | None = None, session_id: str | None = None, working_directory: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target, notebook = self._read_notebook(path)
            try:
                cell = notebook.cells[cell_index]
            except IndexError as exc:
                raise ValidationError("cell_index is out of range", {"cell_index": cell_index}) from exc
            active_session_id = session_id
            if active_session_id is None:
                created = self.session_manager.create_session(str(self.path_manager.resolve_root(working_directory or str(target.parent))))
                active_session_id = created["session_id"]
            result = self.session_manager.execute(active_session_id, cell.source)
            return {"path": str(target), "cell_index": cell_index, "session_id": active_session_id, "execution": result}

        return self._invoke(tool_name="run_notebook_cell", action_category="execute", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"path": path, "cell_index": cell_index, "session_id": session_id, "working_directory": working_directory}, paths=[path])

    def export_notebook_to_python(self, path: str, output_path: str | None = None, token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            target, notebook = self._read_notebook(path)
            destination = self.path_manager.resolve_path(output_path, allow_missing=True) if output_path else target.with_suffix(".py")
            lines = []
            for cell in notebook.cells:
                prefix = "# %%\n"
                lines.append(prefix)
                lines.append(cell.source)
                lines.append("\n\n")
            destination.write_text("".join(lines), encoding="utf-8")
            return {"path": str(target), "output_path": str(destination)}

        return self._invoke(tool_name="export_notebook_to_python", action_category="write", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"path": path, "output_path": output_path}, paths=[path, output_path] if output_path else [path])

    def convert_python_to_notebook(self, path: str, output_path: str | None = None, token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            source = self.path_manager.resolve_path(path)
            destination = self.path_manager.resolve_path(output_path, allow_missing=True) if output_path else source.with_suffix(".ipynb")
            content = source.read_text(encoding="utf-8")
            chunks = [chunk.strip("\n") for chunk in content.split("# %%") if chunk.strip()]
            notebook = nbformat.v4.new_notebook()
            notebook.cells = [nbformat.v4.new_code_cell(chunk.strip()) for chunk in chunks] or [nbformat.v4.new_code_cell(content)]
            self._write_notebook(destination, notebook)
            return {"path": str(source), "output_path": str(destination), "cell_count": len(notebook.cells)}

        return self._invoke(tool_name="convert_python_to_notebook", action_category="write", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"path": path, "output_path": output_path}, paths=[path, output_path] if output_path else [path])

    def duplicate_notebook(self, path: str, destination_path: str, token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            source = self.path_manager.resolve_path(path)
            destination = self.path_manager.resolve_path(destination_path, allow_missing=True)
            destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            return {"source": str(source), "destination": str(destination)}

        return self._invoke(tool_name="duplicate_notebook", action_category="write", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"path": path, "destination_path": destination_path}, paths=[path, destination_path])

    def create_python_session(self, working_directory: str | None = None, token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            cwd = str(self.path_manager.resolve_root(working_directory))
            return self.session_manager.create_session(cwd)

        return self._invoke(tool_name="create_python_session", action_category="execute", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"working_directory": working_directory})

    def execute_in_session(self, session_id: str, code: str, token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            return {"session_id": session_id, "execution": self.session_manager.execute(session_id, code)}

        return self._invoke(tool_name="execute_in_session", action_category="execute", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"session_id": session_id})

    def get_session_variables(self, session_id: str) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            return {"session_id": session_id, **self.session_manager.list_variables(session_id)}

        return self._invoke(tool_name="get_session_variables", action_category="read", operation=operation, args={"session_id": session_id})

    def list_session_variables(self, session_id: str) -> dict[str, Any]:
        return self.get_session_variables(session_id)

    def delete_session_variable(self, session_id: str, name: str, token: str | None = None) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            return {"session_id": session_id, **self.session_manager.delete_variable(session_id, name)}

        return self._invoke(tool_name="delete_session_variable", action_category="write", operation=operation, min_profile=PermissionProfile.DEVELOPER, token=token, args={"session_id": session_id, "name": name})

    def interrupt_session(self, session_id: str, token: str | None = None, confirm: bool = False) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            return self.session_manager.interrupt(session_id)

        return self._invoke(tool_name="interrupt_session", action_category="execute", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, confirm=confirm, destructive=True, args={"session_id": session_id})

    def restart_session(self, session_id: str, token: str | None = None, confirm: bool = False) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            return self.session_manager.restart(session_id)

        return self._invoke(tool_name="restart_session", action_category="execute", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, confirm=confirm, destructive=True, args={"session_id": session_id})

    def close_session(self, session_id: str, token: str | None = None, confirm: bool = False) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            return self.session_manager.close(session_id)

        return self._invoke(tool_name="close_session", action_category="execute", operation=operation, min_profile=PermissionProfile.FULL_CONTROL, token=token, confirm=confirm, destructive=True, args={"session_id": session_id})

    def list_sessions(self) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            return {"sessions": self.session_manager.list_sessions()}

        return self._invoke(tool_name="list_sessions", action_category="read", operation=operation)

    def get_session_status(self, session_id: str) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            return self.session_manager.get_status(session_id)

        return self._invoke(tool_name="get_session_status", action_category="read", operation=operation, args={"session_id": session_id})

    def get_session_output(self, session_id: str) -> dict[str, Any]:
        def operation() -> dict[str, Any]:
            return self.session_manager.get_output(session_id)

        return self._invoke(tool_name="get_session_output", action_category="read", operation=operation, args={"session_id": session_id})
