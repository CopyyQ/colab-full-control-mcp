from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from colab_full_control_mcp.settings import Settings


def main() -> int:
    settings = Settings()
    pid_path = settings.job_root / "mcp_server.pid"
    if not pid_path.exists():
        print("Server PID file not found. Nothing to stop.")
        return 0
    pid = int(pid_path.read_text(encoding="utf-8"))
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Sent termination signal to MCP server pid={pid}")
    except (ProcessLookupError, OSError) as exc:
        print(f"MCP server pid={pid} is not running or could not be signaled ({exc}). Removed stale PID file.")
    finally:
        pid_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
