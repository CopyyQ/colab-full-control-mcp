from __future__ import annotations

import json
from pathlib import Path

from colab_full_control_mcp.tools import build_tool_bundle

from conftest import TEST_TOKEN


def test_delete_requires_confirmation(bundle):
    root = Path(bundle.settings.allowed_roots[0])
    target = root / "delete-me.txt"
    target.write_text("temp", encoding="utf-8")
    response = bundle.file_tools.delete_path(str(target), token=TEST_TOKEN, confirm=False)
    assert response["ok"] is False
    assert response["error"]["type"] == "confirmation_required"


def test_full_control_required_for_raw_shell(settings_factory):
    developer_bundle = build_tool_bundle(settings_factory(permission_profile="DEVELOPER"))
    response = developer_bundle.shell_tools.run_shell_command("echo hi", token=TEST_TOKEN, confirm=True)
    assert response["ok"] is False
    assert response["error"]["type"] == "permission_denied"


def test_audit_redacts_secret_like_arguments(bundle):
    response = bundle.file_tools.create_file("audit.txt", "hello", token=TEST_TOKEN)
    assert response["ok"] is True
    audit_path = Path(bundle.settings.audit_log_path)
    last_record = json.loads(audit_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    serialized = json.dumps(last_record)
    assert TEST_TOKEN not in serialized
    assert "request_id" in last_record
