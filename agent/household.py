"""Бытовые просьбы: человек говорит идею, агент сам выбирает действие."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from agent.memory import MemoryManager
from agent.tool_runner import ToolRunner

_SHOW_NOTES = re.compile(
    r"^(?:что ты помнишь|что помнишь|мои заметки|покажи заметки|покажи память|"
    r"what do you remember)\b",
    re.IGNORECASE,
)
_NOTE = re.compile(
    r"^(?:запомни|запиши|заметка|напомни|не забудь|не забыть|"
    r"сделай заметку|создай заметку|напиши заметку|remember|note)"
    r"\b[\s,:.-]*(?:\b(?:про|о|об|что)\b\s+)?(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_ADD_LIST = re.compile(
    r"^(?:добавь в список|add to list)\s+(\S+)\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_MAKE_LIST = re.compile(
    r"^(?:сделай список|создай список|хочу список|список)\s+([^:]+):\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_SHOW_LIST = re.compile(
    r"^(?:покажи список|мой список)\s+(.+?)\s*$",
    re.IGNORECASE | re.DOTALL,
)
_BARE_LIST = re.compile(r"^список\s+(\S+)\s*$", re.IGNORECASE)
_OPEN = re.compile(r"^(?:открой|открыть|open)\b", re.IGNORECASE)
_OPEN_TARGET = re.compile(
    r"^(?:открой|открыть|open)\s+(?:сайт\s+)?(\S+)\s*$",
    re.IGNORECASE,
)
_URL = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_FILE_SUFFIXES = {".py", ".md", ".txt", ".json", ".toml"}


class Household:
    """Заметки, списки и открытие ссылок без плана и без модели."""

    def __init__(
        self,
        root: str | Path = "home",
        memory: MemoryManager | None = None,
        runner: ToolRunner | None = None,
    ) -> None:
        self.root = Path(root)
        self.memory = memory or MemoryManager(self.root / "memory.json")
        self.runner = runner or ToolRunner()

    async def handle(self, task: str) -> str | None:
        text = " ".join(task.strip().split())
        if not text:
            return None
        if _SHOW_NOTES.match(text):
            return self._show_notes()
        shown = _SHOW_LIST.match(text) or _BARE_LIST.match(text)
        if shown:
            return self._show_list(shown.group(1))
        made = _MAKE_LIST.match(text)
        if made:
            items = [item.strip() for item in re.split(r",|\s+и\s+", made.group(2)) if item.strip()]
            return self._add_items(made.group(1), items)
        added = _ADD_LIST.match(text)
        if added:
            return self._add_items(added.group(1), [added.group(2).strip()])
        note = _NOTE.match(text)
        if note and note.group(1).strip():
            return self._save_note(note.group(1).strip())
        url = _open_url(text)
        if url is not None:
            return await self._open(url)
        return None

    def _save_note(self, text: str) -> str:
        path = self._notes_path()
        existing = _lines(path)
        if text not in existing:
            existing.append(text)
            _write_lines(path, existing)
        self.memory.save_fact(text)
        return f"Запомнил: {text}"

    def _show_notes(self) -> str:
        notes = _lines(self._notes_path())
        memory = [fact for fact in self.memory.load() if not fact.startswith("Успешно выполнена задача:")]
        if not notes and not memory:
            return "Пока ничего не записано."
        parts: list[str] = []
        if notes:
            parts.append("Заметки:\n" + "\n".join(f"- {line}" for line in notes))
        extra = [fact for fact in memory if fact not in notes]
        if extra:
            parts.append("Ещё помню:\n" + "\n".join(f"- {line}" for line in extra))
        return "\n".join(parts)

    def _add_items(self, name: str, items: list[str]) -> str:
        path = self._list_path(name)
        current = _lines(path)
        fresh = [item for item in items if item not in current]
        current.extend(fresh)
        _write_lines(path, current)
        label = name.strip()
        if not fresh:
            return f"В списке «{label}» это уже есть."
        return f"Список «{label}»: " + ", ".join(current)

    def _show_list(self, name: str) -> str:
        items = _lines(self._list_path(name))
        label = name.strip()
        if not items:
            return f"Список «{label}» пуст."
        return f"Список «{label}»:\n" + "\n".join(f"- {item}" for item in items)

    async def _open(self, url: str) -> str:
        code, stdout, stderr = await self.runner.execute(
            f"python -m webbrowser -t {shlex.quote(url)}"
        )
        if code == 0:
            return f"Открываю {url}"
        detail = stderr.strip() or stdout.strip() or f"код {code}"
        return f"Не удалось открыть {url}: {detail}"

    def _notes_path(self) -> Path:
        return self.root / "notes.md"

    def _list_path(self, name: str) -> Path:
        safe = re.sub(r"[\\/]+", " ", name).strip() or "список"
        return self.root / "lists" / f"{safe}.txt"


def _open_url(text: str) -> str | None:
    if _OPEN.match(text) is None:
        return None
    found = _URL.search(text)
    if found:
        return found.group(0).rstrip(".,)")
    match = _OPEN_TARGET.match(text)
    if match is None:
        return None
    target = match.group(1).rstrip(".,)")
    if Path(target).suffix.lower() in _FILE_SUFFIXES:
        return None
    if "." not in target:
        return None
    return "https://" + target


def _lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
