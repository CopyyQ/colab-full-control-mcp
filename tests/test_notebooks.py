from __future__ import annotations

from pathlib import Path

import nbformat

from conftest import TEST_TOKEN


def test_notebook_editing(bundle):
    root = Path(bundle.settings.allowed_roots[0])
    notebook_path = root / "demo.ipynb"
    notebook = nbformat.v4.new_notebook()
    notebook.cells = [nbformat.v4.new_code_cell("x = 1"), nbformat.v4.new_markdown_cell("hello")]
    nbformat.write(notebook, notebook_path)

    listed = bundle.notebook_tools.list_notebook_cells(str(notebook_path))
    assert listed["ok"] is True
    assert len(listed["data"]["cells"]) == 2

    updated = bundle.notebook_tools.update_notebook_cell(str(notebook_path), 0, "x = 2", token=TEST_TOKEN)
    assert updated["ok"] is True
    read_cell = bundle.notebook_tools.read_notebook_cell(str(notebook_path), 0)
    assert read_cell["data"]["cell"]["source"] == "x = 2"


def test_persistent_python_session(bundle):
    created = bundle.notebook_tools.create_python_session(token=TEST_TOKEN)
    assert created["ok"] is True
    session_id = created["data"]["session_id"]

    executed = bundle.notebook_tools.execute_in_session(session_id, "value = 5\nvalue", token=TEST_TOKEN)
    assert executed["ok"] is True
    assert executed["data"]["execution"]["result_repr"] == "5"

    variables = bundle.notebook_tools.get_session_variables(session_id)
    names = [item["name"] for item in variables["data"]["variables"]]
    assert "value" in names

    deleted = bundle.notebook_tools.delete_session_variable(session_id, "value", token=TEST_TOKEN)
    assert deleted["ok"] is True

    closed = bundle.notebook_tools.close_session(session_id, token=TEST_TOKEN, confirm=True)
    assert closed["ok"] is True
