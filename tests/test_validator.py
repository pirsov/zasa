"""L2/L3 валидатора и запись Applier на диск."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent.retriever import CodeRetriever
from agent.schema import ActionType, EditCommand
from agent.validator import Applier, Validator

_SAMPLE = "def foo():\n    return 1\n\ndef bar():\n    return 0\n"


@pytest.fixture
def sample(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "sample.py"
    path.write_text(_SAMPLE, encoding="utf-8")
    return path


def _validator() -> Validator:
    return Validator(CodeRetriever())


def test_l2_missing_file() -> None:
    command = EditCommand(
        action=ActionType.replace_symbol,
        path="missing.py",
        symbol="foo",
        new_code="def foo():\n    return 1\n",
        reason="файла нет",
    )
    ok, error = asyncio.run(_validator().validate(command))
    assert ok is False
    assert error is not None
    assert error.level == "L2"


def test_l2_missing_symbol(sample: Path) -> None:
    command = EditCommand(
        action=ActionType.replace_symbol,
        path="sample.py",
        symbol="missing",
        new_code="def missing():\n    return 1\n",
        reason="символа нет",
    )
    ok, error = asyncio.run(_validator().validate(command))
    assert ok is False
    assert error is not None
    assert error.level == "L2"
    assert error.hint == "Symbol not found in AST outline"
    assert sample.read_text(encoding="utf-8") == _SAMPLE


def test_l3_valid_code(sample: Path) -> None:
    command = EditCommand(
        action=ActionType.replace_symbol,
        path="sample.py",
        symbol="foo",
        new_code="def foo():\n    return 2\n",
        reason="обновить foo",
    )
    assert asyncio.run(_validator().validate(command)) == (True, None)
    assert sample.read_text(encoding="utf-8") == _SAMPLE


def test_l3_invalid_syntax(sample: Path) -> None:
    command = EditCommand(
        action=ActionType.replace_symbol,
        path="sample.py",
        symbol="foo",
        new_code="def foo()\n    return 2\n",
        reason="забыли двоеточие",
    )
    ok, error = asyncio.run(_validator().validate(command))
    assert ok is False
    assert error is not None
    assert error.level == "L3"
    assert "line 1" in error.message
    assert sample.read_text(encoding="utf-8") == _SAMPLE


def test_applier_replace_symbol(sample: Path) -> None:
    command = EditCommand(
        action=ActionType.replace_symbol,
        path="sample.py",
        symbol="foo",
        new_code="def foo():\n    return 2\n",
        reason="заменить foo",
    )
    Applier(CodeRetriever()).apply(command)
    text = sample.read_text(encoding="utf-8")
    assert "def foo():\n    return 2\n" in text
    assert "def bar():\n    return 0\n" in text
    assert "return 1" not in text


def test_applier_replace_method_keeps_indent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "box.py"
    path.write_text(
        "class Box:\n    def foo(self):\n        return 1\n",
        encoding="utf-8",
    )
    Applier(CodeRetriever()).apply(
        EditCommand(
            action=ActionType.replace_symbol,
            path="box.py",
            symbol="foo",
            new_code="def foo(self):\n    return 2\n",
            reason="метод без отступа класса",
        )
    )
    assert path.read_text(encoding="utf-8") == (
        "class Box:\n    def foo(self):\n        return 2\n"
    )


def test_run_check_without_path_passes() -> None:
    command = EditCommand(
        action=ActionType.run_check,
        reason="проверка без файла",
    )
    assert asyncio.run(_validator().validate(command)) == (True, None)


def test_l4_dangerous_command() -> None:
    command = EditCommand(
        action=ActionType.run_command,
        path=".",
        command="rm -rf /",
        reason="опасная команда",
    )
    ok, error = asyncio.run(_validator().validate(command))
    assert ok is False
    assert error is not None
    assert error.level == "L4"
    assert error.message == "Dangerous command blocked"


def test_l4_safe_command() -> None:
    command = EditCommand(
        action=ActionType.run_command,
        path=".",
        command="ls -la",
        reason="список файлов",
    )
    assert asyncio.run(_validator().validate(command)) == (True, None)
