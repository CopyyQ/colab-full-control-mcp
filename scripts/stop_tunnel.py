from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from colab_full_control_mcp.settings import Settings


def main() -> int:
    settings = Settings()
    state_path = settings.job_root / "cloudflared_state.json"
    if not state_path.exists():
        print("Tunnel state file not found.")
        return 1
    state = json.loads(state_path.read_text(encoding="utf-8"))
    pid = int(state["pid"])
    os.kill(pid, signal.SIGTERM)
    state_path.unlink(missing_ok=True)
    print(f"Stopped cloudflared pid={pid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

