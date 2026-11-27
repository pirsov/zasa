"""Персонаж на столе: шаг, разворот и ответ из памяти."""

from __future__ import annotations

import os

import pytest

from agent.desk import Walker, last_reply


def test_walker_moves_and_turns_at_the_edges() -> None:
    walker = Walker(x=0, y=0, screen_w=100, width=40, direction=-1, speed=8)
    walker.step()
    assert walker.x == 0
    assert walker.direction == 1
    walker.x = 70
    walker.step()
    assert walker.x == 60
    assert walker.direction == -1


def test_walker_stands_while_thinking() -> None:
    walker = Walker(x=20, y=0, screen_w=200, state="think", speed=8)
    walker.step()
    assert walker.x == 20
    assert walker.frame == 1


def test_last_reply_is_the_latest_agent_line() -> None:
    facts = [
        "Человек: я хочу пиццу",
        "Агент: Для продолжения нужен город.",
        "Человек: Азов",
    ]
    assert last_reply(facts) == "Для продолжения нужен город."
    assert last_reply(["Человек: да"]) == ""


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="нет экрана")
def test_click_sends_the_phrase_and_shows_the_reply() -> None:
    from agent.desk import Pet

    pet = Pet(run_task=lambda phrase: f"принял: {phrase}", screen_size=(800, 600))
    start = pet.walker.x
    pet.tick()
    assert pet.walker.x != start
    pet._open_chat()
    assert pet._entry is not None
    pet._entry.insert(0, "который час")
    pet._work(pet._entry.get())
    pet.root.update()
    assert pet.walker.state == "talk"
    assert pet.bubble == "принял: который час"
    pet.close()
