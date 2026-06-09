from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import psutil

from .common import ExecutionError, ensure_directory, sanitize_text


class JobManager:
    def __init__(self, db_path: Path, work_dir: Path, max_output_chars: int = 40000):
        self.db_path = db_path.expanduser()
        self.work_dir = ensure_directory(work_dir.expanduser())
        self.max_output_chars = max_output_chars
        ensure_directory(self.db_path.parent)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    pid INTEGER,
                    command_json TEXT NOT NULL,
                    cwd TEXT NOT NULL,
                    env_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    log_path TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    started_at REAL NOT NULL,
                    finished_at REAL,
                    exit_code INTEGER,
                    parent_job_id TEXT
                )
                """
            )

    def _insert_job(
        self,
        *,
        job_id: str,
        kind: str,
        pid: int,
        command: list[str],
        cwd: str,
        env: dict[str, str],
        status: str,
        log_path: str,
        parent_job_id: str | None,
    ) -> None:
        now = time.time()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, kind, pid, command_json, cwd, env_json, status, log_path,
                    created_at, updated_at, started_at, parent_job_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    kind,
                    pid,
                    json.dumps(command),
                    cwd,
                    json.dumps(env),
                    status,
                    log_path,
                    now,
                    now,
                    now,
                    parent_job_id,
                ),
            )

    def _update_status(self, job_id: str, status: str, *, exit_code: int | None = None) -> None:
        now = time.time()
        finished_at = now if status in {"completed", "failed", "stopped"} else None
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, exit_code = COALESCE(?, exit_code), updated_at = ?, finished_at = COALESCE(?, finished_at)
                WHERE job_id = ?
                """,
                (status, exit_code, now, finished_at, job_id),
            )

    def _fetch_job(self, job_id: str) -> sqlite3.Row:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise ExecutionError(f"Unknown job: {job_id}")
        return row

    def _poll(self, row: sqlite3.Row) -> sqlite3.Row:
        status = row["status"]
        pid = row["pid"]
        if status not in {"running", "starting"} or pid is None:
            return row
        try:
            process = psutil.Process(pid)
            return_code = process.wait(timeout=0)
        except psutil.TimeoutExpired:
            return row
        except psutil.NoSuchProcess:
            return_code = row["exit_code"] if row["exit_code"] is not None else 1

        new_status = "completed" if return_code == 0 else "failed"
        self._update_status(row["job_id"], new_status, exit_code=return_code)
        return self._fetch_job(row["job_id"])

    def start_job(
        self,
        *,
        command: list[str],
        cwd: str,
        env: dict[str, str],
        kind: str = "generic",
        log_path: str | None = None,
        parent_job_id: str | None = None,
    ) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        log_target = Path(log_path).expanduser() if log_path else self.work_dir / f"{job_id}.log"
        ensure_directory(log_target.parent)

        creationflags = 0
        kwargs: dict[str, Any] = {}
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            kwargs["creationflags"] = creationflags
        else:
            kwargs["start_new_session"] = True

        with log_target.open("ab") as handle:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=handle,
                stderr=handle,
                **kwargs,
            )

        self._insert_job(
            job_id=job_id,
            kind=kind,
            pid=process.pid,
            command=command,
            cwd=cwd,
            env=env,
            status="running",
            log_path=str(log_target),
            parent_job_id=parent_job_id,
        )
        return self.get_job_status(job_id)

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        row = self._poll(self._fetch_job(job_id))
        return {
            "job_id": row["job_id"],
            "kind": row["kind"],
            "pid": row["pid"],
            "command": json.loads(row["command_json"]),
            "cwd": row["cwd"],
            "status": row["status"],
            "log_path": row["log_path"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "exit_code": row["exit_code"],
            "parent_job_id": row["parent_job_id"],
        }

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT job_id FROM jobs ORDER BY created_at DESC").fetchall()
        return [self.get_job_status(row["job_id"]) for row in rows]

    def get_job_logs(self, job_id: str, tail_chars: int | None = None) -> dict[str, Any]:
        row = self._fetch_job(job_id)
        log_path = Path(row["log_path"])
        content = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        limit = tail_chars or self.max_output_chars
        if tail_chars:
            content = content[-tail_chars:]
            truncated = len(content) == tail_chars
        else:
            content, truncated = sanitize_text(content, self.max_output_chars)
        return {"job_id": job_id, "log_path": str(log_path), "content": content, "truncated": truncated}

    def stream_job_logs(self, job_id: str, offset: int = 0, limit: int = 4000) -> dict[str, Any]:
        row = self._fetch_job(job_id)
        log_path = Path(row["log_path"])
        if not log_path.exists():
            return {"job_id": job_id, "offset": offset, "next_offset": offset, "content": "", "eof": True}
        with log_path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(offset)
            content = handle.read(limit)
            next_offset = handle.tell()
        return {
            "job_id": job_id,
            "offset": offset,
            "next_offset": next_offset,
            "content": content,
            "eof": len(content) < limit,
        }

    def _terminate_tree(self, pid: int) -> int:
        try:
            process = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return 0
        children = process.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except psutil.Error:
                pass
        try:
            process.terminate()
        except psutil.Error:
            pass
        gone, alive = psutil.wait_procs([*children, process], timeout=5)
        for proc in alive:
            try:
                proc.kill()
            except psutil.Error:
                pass
        try:
            return process.wait(timeout=5)
        except psutil.Error:
            return 1

    def stop_job(self, job_id: str) -> dict[str, Any]:
        row = self._fetch_job(job_id)
        pid = row["pid"]
        if pid is None:
            raise ExecutionError(f"Job {job_id} does not have a live process")
        exit_code = self._terminate_tree(pid)
        self._update_status(job_id, "stopped", exit_code=exit_code)
        return self.get_job_status(job_id)

    def wait_for_job(self, job_id: str, timeout_seconds: float | None = None) -> dict[str, Any]:
        started = time.time()
        while True:
            status = self.get_job_status(job_id)
            if status["status"] not in {"running", "starting"}:
                return status
            if timeout_seconds is not None and (time.time() - started) > timeout_seconds:
                raise ExecutionError("Timed out waiting for job", {"job_id": job_id})
            time.sleep(0.2)

    def restart_job(self, job_id: str) -> dict[str, Any]:
        row = self._fetch_job(job_id)
        command = json.loads(row["command_json"])
        env = json.loads(row["env_json"])
        return self.start_job(
            command=command,
            cwd=row["cwd"],
            env=env,
            kind=row["kind"],
            parent_job_id=job_id,
        )

    def delete_job_record(self, job_id: str) -> dict[str, Any]:
        status = self.get_job_status(job_id)
        if status["status"] == "running":
            raise ExecutionError("Cannot delete a running job record", {"job_id": job_id})
        with self._connect() as connection:
            connection.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        return {"job_id": job_id, "deleted": True}
