# Colab Full Control MCP

`colab-full-control-mcp` is a remote MCP server intended to run inside a Google Colab runtime and expose controlled file, code, notebook, runtime, job, Git, Drive, and model-management operations to Codex in VS Code.

## Architecture

```text
VS Code + Codex
-> Remote MCP over Streamable HTTP
-> FastMCP server running in Colab
-> Colab runtime, files, notebooks, jobs, GPU, Drive, Git
```

Default local bind:

- `127.0.0.1:8000`
- MCP endpoint: `http://127.0.0.1:8000/mcp`

Typical public endpoint through Cloudflare Tunnel:

- `https://<subdomain>.trycloudflare.com/mcp`

## What It Covers

The server exposes tool groups for:

- file operations and multi-file patching
- code search and project reading
- safe shell commands and full shell commands
- isolated Python subprocess execution
- persistent Python sessions for notebook-like workflows
- notebook read/edit/run workflows through `nbformat` and `nbclient`
- background jobs with SQLite-backed history
- training, validation, inference, benchmark, and checkpoint helpers
- Git workflows with confirmation gates for destructive behavior
- Google Drive copy and backup helpers
- artifact inspection for CSV, JSON, YAML, images, and archives
- runtime inspection for CPU, GPU, memory, disk, network, and processes

The server does not implement an autonomous research loop. Codex decides how to chain tools after the user gives a task, but the server itself does not invent tasks.

## Security Model

Authentication:

- write and execute tools require `COLAB_MCP_TOKEN`
- read-only tools do not require a token

Permission profiles:

- `READ_ONLY`
- `DEVELOPER`
- `FULL_CONTROL`

Default profile:

- `DEVELOPER`

Default allowed roots:

- `/content`
- `/content/drive/MyDrive`

Safety controls:

- blocks path traversal and null bytes
- resolves symlinks and rejects escapes from allowed roots
- blocks direct access to `/proc`, `/sys`, `/etc`, metadata endpoints, and similar system paths
- requires `confirm=true` for destructive actions such as deletes, force push, killing managed jobs, and notebook cell deletion
- redacts secret-like fields from audit logs

`UNRESTRICTED_RUNTIME_MODE=false` by default. When set to `true`, path restrictions are relaxed, but system-path and secret protections still apply.

## Repository Layout

```text
colab-full-control-mcp/
├── README.md
├── pyproject.toml
├── requirements.txt
├── .env.example
├── .gitignore
├── config.example.toml
├── src/colab_full_control_mcp/
├── scripts/
├── notebooks/
└── tests/
```

## Quick Start In Colab

1. Open `notebooks/colab_full_control_setup.ipynb`.
2. Mount Drive if you need Drive-backed storage.
3. Clone or upload this repository into `/content`.
4. Install dependencies with `pip install -r requirements.txt`.
5. Set `COLAB_MCP_TOKEN` with `getpass`.
6. Start the MCP server on `127.0.0.1:8000`.
7. Run `python scripts/health_check.py`.
8. Install and start `cloudflared`.
9. Print the Codex config with `python scripts/print_codex_config.py --url https://.../mcp`.
10. Add the generated MCP server entry to Codex in VS Code.

## Local Commands

Start the server in the foreground:

```bash
python scripts/start_server.py
```

Start the server in the background:

```bash
python scripts/start_server.py --background
```

Stop the server:

```bash
python scripts/stop_server.py
```

Health check:

```bash
python scripts/health_check.py
```

Start a Cloudflare Tunnel:

```bash
python scripts/start_tunnel.py --server-url http://127.0.0.1:8000
```

Stop the tunnel:

```bash
python scripts/stop_tunnel.py
```

Print Codex MCP config:

```bash
python scripts/print_codex_config.py --url https://example.trycloudflare.com/mcp
```

## Colab And Notebook Notes

The normal Colab/Jupyter browser UI and this MCP server can run side by side, but they are not the same execution channel.

Important implications:

- a persistent MCP Python session is not guaranteed to be the same kernel as the notebook open in the browser
- notebook UI variables and MCP session variables can diverge
- use files, logs, checkpoints, and artifacts as the synchronization boundary
- avoid editing the same notebook or code file from the UI and from MCP at the same time

## Testing

Run the unit tests locally:

```bash
python -m pytest
```

Current test coverage includes:

- auth and permission enforcement
- path traversal and symlink escape checks
- file read/write and rollback behavior
- unified diff patching
- shell filtering and timeout handling
- background job lifecycle and process-tree termination
- notebook editing and persistent sessions
- Git safety checks
- Drive behavior
- output truncation and audit redaction

## Notes On Remote Auth

The implementation today validates `COLAB_MCP_TOKEN` inside write and execute tool inputs. If your Codex build later supports official bearer-header mapping for remote MCP, prefer that transport-level auth and keep the tool-level token path only as a compatibility fallback.
