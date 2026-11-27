"""Инструменты агента: один вызов делает одно действие."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.hands import Hands


@pytest.mark.asyncio
async def test_ask_returns_the_question_and_remember_writes_a_note(tmp_path: Path) -> None:
    hands = Hands(tmp_path)
    question = await hands.call("ask", {"text": "В каком городе доставить?"})
    assert question == "В каком городе доставить?"
    remembered = await hands.call("remember", {"text": "купить молоко"})
    assert remembered == "Запомнил: купить молоко"
    assert (tmp_path / "notes.md").read_text(encoding="utf-8") == "купить молоко\n"


@pytest.mark.asyncio
async def test_agent_clicks_and_types_one_step_at_a_time(tmp_path: Path) -> None:
    page = tmp_path / "form.html"
    page.write_text(
        """<!doctype html><html><head><meta charset="utf-8"></head><body>
        <input name="address" placeholder="Адрес">
        <button onclick="document.body.dataset.sent='1'">Дальше</button>
        </body></html>""",
        encoding="utf-8",
    )
    hands = Hands(tmp_path)
    try:
        opened = await hands.call("open_page", {"url": page.as_uri()})
        assert "Дальше" in opened
        typed = await hands.call("type_text", {"field": "address", "value": "Тверская 1"})
        assert "Ввёл" in typed
        clicked = await hands.call("click", {"text": "Дальше"})
        assert "Нажал" in clicked
        seen = await hands.call("read_page")
        assert "Тверская 1" in seen
    finally:
        await hands.close()
