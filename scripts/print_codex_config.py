from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--server-name", default="colab_full")
    args = parser.parse_args()
    print(f"[mcp_servers.{args.server_name}]")
    print(f'url = "{args.url}"')
    print("")
    print("# This server expects COLAB_MCP_TOKEN inside write/execute tool inputs.")
    print("# If your Codex build later supports bearer headers for remote MCP,")
    print("# add the official auth mapping there instead of passing token fields.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
