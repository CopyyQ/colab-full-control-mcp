from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from colab_full_control_mcp.settings import Settings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=None)
    args = parser.parse_args()
    settings = Settings()
    url = args.url or f"http://{settings.host}:{settings.port}{settings.mount_path}"
    request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json, text/event-stream"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            print(f"Health check OK: {url} status={response.status}")
            return 0
    except urllib.error.HTTPError as exc:
        if exc.code < 500:
            print(f"Health check OK: {url} status={exc.code}")
            return 0
        print(f"Health check failed: {url} status={exc.code}")
        return 1
    except Exception as exc:
        print(f"Health check failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

