from __future__ import annotations

from pathlib import Path

from colab_full_control_mcp.tools import build_tool_bundle

from conftest import TEST_TOKEN


def test_write_requires_token(bundle):
    response = bundle.file_tools.create_file("missing-token.txt", "hello")
    assert response["ok"] is False
    assert response["error"]["type"] == "auth_error"


def test_read_only_profile_blocks_write(settings_factory):
    limited_bundle = build_tool_bundle(settings_factory(permission_profile="READ_ONLY"))
    response = limited_bundle.file_tools.create_file("blocked.txt", "hello", token=TEST_TOKEN)
    assert response["ok"] is False
    assert response["error"]["type"] == "permission_denied"


def test_read_operation_works_without_token(bundle):
    root = Path(bundle.settings.allowed_roots[0])
    sample = root / "sample.txt"
    sample.write_text("hello", encoding="utf-8")
    response = bundle.file_tools.read_file(str(sample))
    assert response["ok"] is True
    assert response["data"]["content"] == "hello"
