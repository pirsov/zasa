"""Долговременная память: факты между запусками агента."""

from __future__ import annotations

import json
from pathlib import Path


class MemoryManager:
    """Хранит список фактов в JSON-файле."""

    def __init__(self, path: str | Path = "plans/memory.json") -> None:
        self.path = Path(path)

    def load(self) -> list[str]:
        if not self.path.is_file():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        return [str(item) for item in raw]

    def save_fact(self, fact: str) -> None:
        facts = self.load()
        if fact in facts:
            return
        facts.append(fact)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(facts, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def get_context(self, max_facts: int = 5) -> str:
        return "\n".join(self.load()[-max_facts:])
