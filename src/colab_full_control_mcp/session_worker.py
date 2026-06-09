from __future__ import annotations

import ast
import contextlib
import io
import json
import sys
from typing import Any


MAX_REPR = 400
SESSION_GLOBALS: dict[str, Any] = {"__name__": "__colab_mcp_session__"}


def safe_repr(value: Any) -> str:
    try:
        text = repr(value)
    except Exception:
        text = f"<unrepresentable {type(value).__name__}>"
    if len(text) > MAX_REPR:
        return text[:MAX_REPR] + "...<truncated>"
    return text


def list_variables() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for key, value in SESSION_GLOBALS.items():
        if key.startswith("__"):
            continue
        items.append({"name": key, "type": type(value).__name__, "repr": safe_repr(value)})
    return sorted(items, key=lambda item: item["name"])


def execute_code(code: str) -> dict[str, Any]:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    result_repr = None
    with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
        tree = ast.parse(code, mode="exec")
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            expression = ast.Expression(tree.body[-1].value)
            tree.body = tree.body[:-1]
            if tree.body:
                exec(compile(tree, "<session>", "exec"), SESSION_GLOBALS, SESSION_GLOBALS)
            result = eval(compile(expression, "<session>", "eval"), SESSION_GLOBALS, SESSION_GLOBALS)
            result_repr = safe_repr(result)
        else:
            exec(compile(tree, "<session>", "exec"), SESSION_GLOBALS, SESSION_GLOBALS)
    return {
        "stdout": stdout_buffer.getvalue(),
        "stderr": stderr_buffer.getvalue(),
        "result_repr": result_repr,
        "variables": list_variables(),
    }


def handle_request(request: dict[str, Any]) -> dict[str, Any]:
    action = request["action"]
    if action == "ping":
        return {"ok": True, "status": "running"}
    if action == "execute":
        return {"ok": True, **execute_code(request["code"])}
    if action in {"list_vars", "get_vars"}:
        return {"ok": True, "variables": list_variables()}
    if action == "delete_var":
        name = request["name"]
        deleted = SESSION_GLOBALS.pop(name, None) is not None
        return {"ok": True, "deleted": deleted, "variables": list_variables()}
    if action == "close":
        return {"ok": True, "closing": True}
    raise ValueError(f"Unsupported action: {action}")


def main() -> int:
    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            request = json.loads(raw_line)
            response = handle_request(request)
        except BaseException as exc:
            response = {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
        sys.stdout.write(json.dumps(response, ensure_ascii=True) + "\n")
        sys.stdout.flush()
        if response.get("closing"):
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

