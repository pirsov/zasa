"""Запуск команд оболочки и таймаут."""

from __future__ import annotations

import asyncio

from agent.tool_runner import ToolRunner


def test_execute_echo() -> None:
    code, stdout, stderr = asyncio.run(ToolRunner().execute('echo "hello"'))
    assert code == 0
    assert stdout == "hello\n"
    assert stderr == ""


def test_execute_fail() -> None:
    code, _stdout, _stderr = asyncio.run(
        ToolRunner().execute('python -c "import sys; sys.exit(1)"')
    )
    assert code == 1


def test_timeout() -> None:
    code, stdout, stderr = asyncio.run(ToolRunner(timeout=0.2).execute("sleep 5"))
    assert code == 124
    assert stdout == ""
    assert "timed out" in stderr.lower()
