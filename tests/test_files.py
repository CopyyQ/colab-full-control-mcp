from __future__ import annotations

import os
from pathlib import Path

import pytest

from colab_full_control_mcp.tools import build_tool_bundle

from conftest import TEST_TOKEN


def test_path_traversal_is_blocked(bundle):
    outside = Path(bundle.settings.allowed_roots[0]).parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    response = bundle.file_tools.read_file("../outside.txt")
    assert response["ok"] is False
    assert response["error"]["type"] == "path_safety_error"


def test_symlink_escape_is_blocked(bundle):
    root = Path(bundle.settings.allowed_roots[0])
    outside = root.parent / "escape.txt"
    outside.write_text("secret", encoding="utf-8")
    link = root / "link.txt"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is not available in this environment")
    response = bundle.file_tools.read_file(str(link))
    assert response["ok"] is False
    assert response["error"]["type"] == "path_safety_error"


def test_file_read_write_and_hash(bundle):
    create = bundle.file_tools.create_file("notes.txt", "alpha", token=TEST_TOKEN)
    assert create["ok"] is True
    append = bundle.file_tools.append_file("notes.txt", "\nbeta", token=TEST_TOKEN)
    assert append["ok"] is True
    read = bundle.file_tools.read_file("notes.txt")
    assert read["data"]["content"] == "alpha\nbeta"
    digest = bundle.file_tools.calculate_hash("notes.txt")
    assert digest["ok"] is True
    assert len(digest["data"]["hash"]) == 64


def test_apply_unified_diff(bundle):
    root = Path(bundle.settings.allowed_roots[0])
    target = root / "code.py"
    target.write_text("value = 1\nprint(value)\n", encoding="utf-8")
    diff = """--- a/code.py
+++ b/code.py
@@ -1,2 +1,2 @@
-value = 1
+value = 2
 print(value)
"""
    response = bundle.file_tools.apply_unified_diff(diff, token=TEST_TOKEN)
    assert response["ok"] is True
    assert "code.py" in target.read_text(encoding="utf-8") or target.read_text(encoding="utf-8").startswith("value = 2")
    assert target.read_text(encoding="utf-8") == "value = 2\nprint(value)\n"


def test_multi_file_patch_rolls_back_on_failure(bundle):
    root = Path(bundle.settings.allowed_roots[0])
    first = root / "a.txt"
    second = root / "b.txt"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")
    response = bundle.file_tools.multi_file_patch(
        [
            {"path": str(first), "search_text": "one", "replacement": "ONE"},
            {"path": str(second), "search_text": "missing", "replacement": "TWO"},
        ],
        token=TEST_TOKEN,
    )
    assert response["ok"] is False
    assert first.read_text(encoding="utf-8") == "one"
    assert second.read_text(encoding="utf-8") == "two"


def test_read_file_truncates_output(settings_factory):
    tiny_bundle = build_tool_bundle(settings_factory(max_read_bytes=8))
    root = Path(tiny_bundle.settings.allowed_roots[0])
    target = root / "big.txt"
    target.write_text("0123456789abcdef", encoding="utf-8")
    response = tiny_bundle.file_tools.read_file(str(target))
    assert response["ok"] is True
    assert response["truncated"] is True
    assert response["data"]["content"] == "01234567"
