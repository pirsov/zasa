"""Результат называет человек. Способ получить его выбирает агент."""

from __future__ import annotations

import ast
import re
from pathlib import Path

_INTENT = re.compile(
    r"\b(создай|сделай|напиши|добавь|нужн\w*|замени|реализуй|хочу|исправь|поменяй)\b",
    re.IGNORECASE,
)
_FUNC_NAME = re.compile(r"функци\w*\s+([A-Za-z_]\w*)", re.IGNORECASE)
_PY_PATH = re.compile(r"[\w./\\-]+\.py")
_RETURN = re.compile(
    r"возвраща\w*\s+(?:строку\s+|число\s+)?(?:['\"]([^'\"]+)['\"]|([^\s.,;]+))",
    re.IGNORECASE,
)


class Outcomes:
    """Собирает файл с функцией, если в просьбе уже есть нужный результат."""

    def __init__(self, root: str | Path = ".") -> None:
        self.root = Path(root)

    def achieve(self, task: str) -> str | None:
        text = " ".join(task.strip().split())
        if not text or _INTENT.search(text) is None:
            return None
        found = _FUNC_NAME.search(text)
        if found is None:
            return None
        name = found.group(1)
        path = _safe_path(_PY_PATH.search(text), name)
        if path is None:
            return None
        value = _return_value(text)
        target = self.root / path
        source = target.read_text(encoding="utf-8") if target.is_file() else ""
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_upsert(source, name, value), encoding="utf-8")
        shown = "ничего" if value is None else value
        return f"Готово: {name}() в {path} возвращает {shown}."


def _safe_path(match: re.Match[str] | None, name: str) -> str | None:
    raw = match.group(0) if match is not None else f"{name}.py"
    normalized = raw.replace("\\", "/")
    if normalized.startswith("/") or ".." in normalized.split("/"):
        return None
    return normalized


def _return_value(text: str) -> str | None:
    found = _RETURN.search(text)
    if found is None:
        return None
    return found.group(1) or found.group(2)


def _upsert(source: str, name: str, value: str | None) -> str:
    rendered = _render(name, value)
    if not source.strip():
        return rendered
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source.rstrip() + "\n\n" + rendered
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return _replace_span(source, node.lineno, node.end_lineno or node.lineno, rendered)
    return source.rstrip() + "\n\n" + rendered


def _render(name: str, value: str | None) -> str:
    if value is None:
        body = "pass"
    elif re.fullmatch(r"-?\d+", value):
        body = f"return {value}"
    else:
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        body = f"return '{escaped}'"
    return f"def {name}():\n    {body}\n"


def _replace_span(source: str, start: int, end: int, rendered: str) -> str:
    lines = source.splitlines()
    updated = lines[: start - 1] + rendered.splitlines() + lines[end:]
    suffix = "\n" if source.endswith("\n") else ""
    return "\n".join(updated) + suffix
