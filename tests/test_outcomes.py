"""Человек называет результат, агент сам собирает файл."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.outcomes import Outcomes


def test_creates_function_from_the_result(tmp_path: Path) -> None:
    message = Outcomes(tmp_path).achieve(
        "сделай hello.py с функцией hello которая возвращает hello"
    )
    assert message == "Готово: hello() в hello.py возвращает hello."
    namespace: dict[str, object] = {}
    exec((tmp_path / "hello.py").read_text(encoding="utf-8"), namespace)
    assert namespace["hello"]() == "hello"


def test_adds_function_without_removing_the_old_one(tmp_path: Path) -> None:
    outcomes = Outcomes(tmp_path)
    outcomes.achieve("сделай hello.py с функцией hello которая возвращает hello")
    outcomes.achieve("добавь в hello.py функцию goodbye которая возвращает goodbye")
    namespace: dict[str, object] = {}
    exec((tmp_path / "hello.py").read_text(encoding="utf-8"), namespace)
    assert namespace["hello"]() == "hello"
    assert namespace["goodbye"]() == "goodbye"


def test_replaces_existing_function(tmp_path: Path) -> None:
    outcomes = Outcomes(tmp_path)
    outcomes.achieve("сделай hello.py с функцией hello которая возвращает hello")
    outcomes.achieve("исправь в hello.py функцию hello чтобы возвращала 2")
    namespace: dict[str, object] = {}
    exec((tmp_path / "hello.py").read_text(encoding="utf-8"), namespace)
    assert namespace["hello"]() == 2


def test_picks_a_filename_when_the_user_did_not(tmp_path: Path) -> None:
    message = Outcomes(tmp_path).achieve("нужна функция ping которая возвращает pong")
    assert message == "Готово: ping() в ping.py возвращает pong."
    assert (tmp_path / "ping.py").is_file()


def test_reading_is_not_a_result_to_build(tmp_path: Path) -> None:
    assert Outcomes(tmp_path).achieve("прочитай функцию hello в hello.py") is None


@pytest.mark.asyncio
async def test_orchestrator_builds_the_result_without_a_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.test_orchestrator import _orchestrator

    monkeypatch.chdir(tmp_path)
    orchestrator = _orchestrator(tmp_path)
    orchestrator.outcomes = Outcomes(tmp_path)
    await orchestrator.run("сделай hello.py с функцией hello которая возвращает hello")
    orchestrator.planner.create_plan.assert_not_awaited()
    assert (tmp_path / "hello.py").is_file()
