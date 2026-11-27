"""Валидатор L1–L4 и безопасное применение EditCommand к файлам."""

from __future__ import annotations

import ast
import tempfile
from pathlib import Path

from agent.retriever import CodeRetriever
from agent.schema import ActionType, EditCommand, ValidatorError

_SYMBOL_ACTIONS = frozenset(
    {ActionType.replace_symbol, ActionType.insert_after_symbol}
)
_BLOCKED_COMMANDS = (
    "rm -rf /",
    "mkfs",
    "dd if=",
    ":(){ :|:& };:",
    "shutdown",
    "reboot",
)


class Applier:
    """Применяет EditCommand к файлу. Оригинал не трогает, пока не вызван apply."""

    def __init__(self, retriever: CodeRetriever) -> None:
        self._retriever = retriever

    def apply(self, command: EditCommand) -> None:
        path = Path(command.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self._render(command), encoding="utf-8")

    def apply_to_temp(self, command: EditCommand) -> str:
        """Пишет результат во временный файл и возвращает его текст."""
        content = self._render(command)
        with tempfile.TemporaryDirectory(prefix="jarvis-apply-") as directory:
            temp_path = Path(directory) / Path(command.path).name
            temp_path.write_text(content, encoding="utf-8")
            return temp_path.read_text(encoding="utf-8")

    def _render(self, command: EditCommand) -> str:
        if command.action == ActionType.write_file:
            return command.new_code or ""
        original = Path(command.path).read_text(encoding="utf-8")
        if command.action == ActionType.replace_symbol:
            return self._replace(command, original)
        if command.action == ActionType.insert_after_symbol:
            return self._insert_after(command, original)
        return original

    def _replace(self, command: EditCommand, original: str) -> str:
        start, end, base_indent = self._symbol_span(command, original)
        lines = original.splitlines()
        updated = lines[:start] + _with_base_indent(command.new_code or "", base_indent)
        updated.extend(lines[end + 1 :])
        return _join_like(original, updated)

    def _insert_after(self, command: EditCommand, original: str) -> str:
        _start, end, base_indent = self._symbol_span(command, original)
        lines = original.splitlines()
        inserted = _with_base_indent(command.new_code or "", base_indent)
        updated = lines[: end + 1] + [""] + inserted + lines[end + 1 :]
        return _join_like(original, updated)

    def _symbol_span(
        self, command: EditCommand, original: str
    ) -> tuple[int, int, str]:
        symbol = command.symbol or ""
        source = self._retriever.get_symbol(command.path, symbol)
        if source is None:
            raise ValueError(f"Symbol not found: {symbol}")
        block = source.splitlines()
        found = _find_block(original.splitlines(), block)
        if found is None:
            raise ValueError(f"Symbol block not found in file: {symbol}")
        start, end = found
        base_indent = _indent_of(block[0]) if block else ""
        return start, end, base_indent


class Validator:
    """Три уровня проверки команды перед записью на диск."""

    def __init__(self, retriever: CodeRetriever) -> None:
        self._retriever = retriever
        self._applier = Applier(retriever)

    async def validate(
        self, command: EditCommand
    ) -> tuple[bool, ValidatorError | None]:
        if not isinstance(command, EditCommand):
            return False, ValidatorError(
                level="L1",
                message="command is not an EditCommand",
                hint="Build the command with the EditCommand schema",
            )

        if command.action == ActionType.call_mcp:
            return True, None

        if command.action == ActionType.run_command:
            blocked = _blocked_command(command.command or "")
            if blocked is not None:
                return False, ValidatorError(
                    level="L4",
                    message="Dangerous command blocked",
                    hint=f"Blocked pattern: {blocked}",
                )
            return True, None

        if command.action != ActionType.write_file and not Path(command.path).is_file():
            return False, ValidatorError(
                level="L2",
                message=f"File not found: {command.path}",
                hint="Check the path or create the file with write_file",
            )

        if command.action in _SYMBOL_ACTIONS:
            outline = self._retriever.get_outline(command.path)
            names = {item["name"] for item in outline}
            if command.symbol not in names:
                return False, ValidatorError(
                    level="L2",
                    message=f"Symbol not found: {command.symbol}",
                    hint="Symbol not found in AST outline",
                )

        try:
            temp_content = self._applier.apply_to_temp(command)
            ast.parse(temp_content)
        except SyntaxError as exc:
            line = exc.lineno if exc.lineno is not None else "?"
            text = exc.msg or "invalid syntax"
            return False, ValidatorError(
                level="L3",
                message=f"{text} (line {line})",
                hint="Fix the Python syntax in new_code before applying",
            )
        return True, None


def _blocked_command(command: str) -> str | None:
    folded = " ".join(command.lower().split())
    for pattern in _BLOCKED_COMMANDS:
        if pattern in command or pattern in folded:
            return pattern
    return None


def _find_block(lines: list[str], block: list[str]) -> tuple[int, int] | None:
    if not block:
        return None
    last = len(lines) - len(block) + 1
    for start in range(last):
        if lines[start : start + len(block)] == block:
            return start, start + len(block) - 1
    return None


def _indent_of(line: str) -> str:
    stripped = line.lstrip(" \t")
    return line[: len(line) - len(stripped)]


def _with_base_indent(new_code: str, base_indent: str) -> list[str]:
    lines = new_code.splitlines()
    if not base_indent:
        return lines
    first = next((line for line in lines if line.strip()), "")
    if first.startswith(base_indent):
        return lines
    aligned: list[str] = []
    for line in lines:
        if line.strip():
            aligned.append(base_indent + line)
        else:
            aligned.append("")
    return aligned


def _join_like(original: str, lines: list[str]) -> str:
    text = "\n".join(lines)
    if original.endswith("\n"):
        text += "\n"
    return text
