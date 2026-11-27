"""Память: загрузка, запись и отказ от повторов."""

from __future__ import annotations

from pathlib import Path

from agent.memory import MemoryManager


def test_load_missing_file(tmp_path: Path) -> None:
    memory = MemoryManager(tmp_path / "memory.json")
    assert memory.load() == []
    assert memory.get_context() == ""


def test_save_and_load_facts(tmp_path: Path) -> None:
    memory = MemoryManager(tmp_path / "memory.json")
    memory.save_fact("первый факт")
    memory.save_fact("второй факт")
    assert memory.load() == ["первый факт", "второй факт"]
    assert memory.get_context() == "первый факт\nвторой факт"


def test_save_fact_skips_duplicates(tmp_path: Path) -> None:
    memory = MemoryManager(tmp_path / "memory.json")
    memory.save_fact("один")
    memory.save_fact("один")
    memory.save_fact("два")
    memory.save_fact("один")
    assert memory.load() == ["один", "два"]


def test_get_context_returns_last_facts(tmp_path: Path) -> None:
    memory = MemoryManager(tmp_path / "memory.json")
    for index in range(6):
        memory.save_fact(f"факт {index}")
    assert memory.get_context(max_facts=2) == "факт 4\nфакт 5"
