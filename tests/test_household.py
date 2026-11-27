"""Бытовые просьбы выполняются без плана и без модели."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agent.household import Household
from agent.memory import MemoryManager


def _household(tmp_path: Path) -> Household:
    memory = MemoryManager(tmp_path / "memory.json")
    runner = AsyncMock()
    runner.execute = AsyncMock(return_value=(0, "", ""))
    return Household(tmp_path / "home", memory, runner)


@pytest.mark.asyncio
async def test_remember_and_show(tmp_path: Path) -> None:
    home = _household(tmp_path)
    assert await home.handle("запомни купить молоко") == "Запомнил: купить молоко"
    assert await home.handle("запомни купить молоко") == "Запомнил: купить молоко"
    shown = await home.handle("что ты помнишь")
    assert shown is not None
    assert "купить молоко" in shown
    assert (tmp_path / "home" / "notes.md").read_text(encoding="utf-8").count("купить молоко") == 1


@pytest.mark.asyncio
async def test_shopping_list(tmp_path: Path) -> None:
    home = _household(tmp_path)
    created = await home.handle("хочу список покупок: молоко, хлеб и яйца")
    assert created is not None
    assert "молоко" in created
    assert "яйца" in created
    assert await home.handle("добавь в список покупок сыр")
    shown = await home.handle("покажи список покупок")
    assert shown is not None
    assert "сыр" in shown


@pytest.mark.asyncio
async def test_open_url_uses_runner(tmp_path: Path) -> None:
    home = _household(tmp_path)
    answer = await home.handle("открой сайт example.com")
    assert answer == "Открываю https://example.com"
    command = home.runner.execute.await_args.args[0]
    assert "https://example.com" in command


@pytest.mark.asyncio
async def test_code_idea_is_not_household(tmp_path: Path) -> None:
    home = _household(tmp_path)
    assert await home.handle("добавь функцию hello в hello.py") is None
    assert await home.handle("открой hello.py") is None
