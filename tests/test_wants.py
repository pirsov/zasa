"""«Я хочу пиццу» заканчивается страницей заказа, без плана и без модели."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agent.wants import Wants


def _wants() -> Wants:
    runner = AsyncMock()
    runner.execute = AsyncMock(return_value=(0, "", ""))
    return Wants(runner)


@pytest.mark.asyncio
async def test_pizza_opens_moscow_menu() -> None:
    wants = _wants()
    answer = await wants.fulfill("я хочу пиццу")
    assert answer is not None
    assert "пиццу" in answer
    assert "https://papajohns.ru/moscow" in answer
    command = wants.runner.execute.await_args.args[0]
    assert "https://papajohns.ru/moscow" in command


@pytest.mark.asyncio
async def test_other_want_goes_to_search() -> None:
    answer = await _wants().fulfill("хочу наушники")
    assert answer is not None
    assert "наушники" in answer
    assert "yandex.ru/search" in answer


@pytest.mark.asyncio
async def test_list_and_code_are_not_wants() -> None:
    wants = _wants()
    assert await wants.fulfill("хочу список покупок: молоко") is None
    assert await wants.fulfill("сделай hello.py с функцией hello") is None


@pytest.mark.asyncio
async def test_orchestrator_orders_pizza_without_a_plan(tmp_path: Path) -> None:
    from tests.test_orchestrator import _orchestrator

    orchestrator = _orchestrator(tmp_path)
    orchestrator.wants = _wants()
    await orchestrator.run("я хочу пиццу")
    orchestrator.planner.create_plan.assert_not_awaited()
    assert any("пиццу" in fact for fact in orchestrator.memory.load())
