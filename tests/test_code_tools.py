from __future__ import annotations

from pathlib import Path


def test_search_code_returns_context(bundle):
    root = Path(bundle.settings.allowed_roots[0])
    file_path = root / "app.py"
    file_path.write_text("a = 1\nmagic_value = 42\nprint(magic_value)\n", encoding="utf-8")
    response = bundle.code_tools.search_code(str(root), "magic_value")
    assert response["ok"] is True
    assert response["data"]["results"][0]["line_number"] == 2
    assert "magic_value = 42" in response["data"]["results"][0]["line"]


def test_read_project_paginates(bundle):
    root = Path(bundle.settings.allowed_roots[0])
    (root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (root / "README.md").write_text("# Demo\n", encoding="utf-8")
    (root / "module.py").write_text("print('hi')\n", encoding="utf-8")
    response = bundle.code_tools.read_project(str(root), page=1, page_size=2)
    assert response["ok"] is True
    assert response["data"]["page_size"] == 2
    assert len(response["data"]["entries"]) == 2
