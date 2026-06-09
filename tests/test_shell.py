from __future__ import annotations

import sys

from conftest import TEST_TOKEN


def test_run_safe_command(bundle):
    response = bundle.shell_tools.run_safe_command([sys.executable, "-c", "print('ok')"], token=TEST_TOKEN)
    assert response["ok"] is True
    assert response["data"]["stdout"].strip() == "ok"


def test_shell_filtering_blocks_dangerous_commands(bundle):
    response = bundle.shell_tools.run_shell_command("shutdown now", token=TEST_TOKEN, confirm=True)
    assert response["ok"] is False
    assert response["error"]["type"] == "validation_error"


def test_subprocess_timeout_is_reported(bundle):
    response = bundle.shell_tools.run_safe_command([sys.executable, "-c", "import time; time.sleep(2)"], timeout=1, token=TEST_TOKEN)
    assert response["ok"] is False
    assert response["error"]["type"] == "execution_error"
