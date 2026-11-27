"""Извлечение символов из исходников через tree-sitter."""

from __future__ import annotations

from pathlib import Path

import tree_sitter_language_pack
from tree_sitter import Node, Tree

_DEFINITION_TYPES = frozenset({"function_definition", "class_definition"})


class CodeRetriever:
    """Достаёт из файла только нужные функции и классы, без остального модуля."""

    def __init__(self) -> None:
        self._parser = tree_sitter_language_pack.get_parser("python")

    def get_outline(self, file_path: str) -> list[dict]:
        """Все верхнеуровневые функции и классы файла."""
        _, tree = self._parse(file_path)
        root = tree.root_node
        if root.has_error:
            return []

        outline: list[dict] = []
        for child in root.children:
            definition, span = _top_level_definition(child)
            if definition is None or span is None:
                continue
            name = _node_name(definition)
            if name is None:
                continue
            start_line, end_line = _line_span(span)
            kind = "function" if definition.type == "function_definition" else "class"
            outline.append(
                {
                    "name": name,
                    "type": kind,
                    "start_line": start_line,
                    "end_line": end_line,
                }
            )
        return outline

    def get_symbol(self, file_path: str, symbol_name: str) -> str | None:
        """Полный исходник функции, метода или класса, с исходными отступами."""
        text, tree = self._parse(file_path)
        found = _find_definition(tree.root_node, symbol_name)
        if found is None:
            return None
        start_line, end_line = _line_span(_definition_span(found))
        return _join_lines(text, start_line, end_line)

    def get_signature_and_context(
        self,
        file_path: str,
        symbol_name: str,
        context_lines: int = 2,
    ) -> str | None:
        """Сигнатура `def`/`class` и несколько следующих строк тела."""
        text, tree = self._parse(file_path)
        found = _find_definition(tree.root_node, symbol_name)
        if found is None:
            return None

        span = _definition_span(found)
        lines = text.splitlines()
        start_row = span.start_point.row
        header_last = _header_last_row(span)
        symbol_last = _last_row(span)
        context_last = min(header_last + max(context_lines, 0), symbol_last)
        return "\n".join(lines[start_row : context_last + 1])

    def _parse(self, file_path: str) -> tuple[str, Tree]:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(file_path)
        source = path.read_bytes()
        return source.decode("utf-8"), self._parser.parse(source)


def _top_level_definition(node: Node) -> tuple[Node | None, Node | None]:
    if node.type == "decorated_definition":
        for child in node.children:
            if child.type in _DEFINITION_TYPES:
                return child, node
        return None, None
    if node.type in _DEFINITION_TYPES:
        return node, node
    return None, None


def _find_definition(root: Node, symbol_name: str) -> Node | None:
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in _DEFINITION_TYPES and _node_name(node) == symbol_name:
            return node
        stack.extend(reversed(node.children))
    return None


def _definition_span(node: Node) -> Node:
    parent = node.parent
    if parent is not None and parent.type == "decorated_definition":
        return parent
    return node


def _node_name(node: Node) -> str | None:
    name = node.child_by_field_name("name")
    if name is None or name.text is None:
        return None
    return name.text.decode("utf-8")


def _line_span(node: Node) -> tuple[int, int]:
    return node.start_point.row + 1, _last_row(node) + 1


def _last_row(node: Node) -> int:
    """Последняя занятая строка, 0-индексация tree-sitter."""
    if node.end_point.column == 0 and node.end_point.row > node.start_point.row:
        return node.end_point.row - 1
    return node.end_point.row


def _header_last_row(node: Node) -> int:
    """Строка, на которой заканчивается заголовок `def`/`class` (0-индексация)."""
    body = node.child_by_field_name("body")
    if node.type == "decorated_definition":
        for child in node.children:
            if child.type in _DEFINITION_TYPES:
                body = child.child_by_field_name("body")
                break
    if body is not None and body.start_point.row > node.start_point.row:
        return body.start_point.row - 1
    return node.start_point.row


def _join_lines(text: str, start_line: int, end_line: int) -> str:
    lines = text.splitlines()
    return "\n".join(lines[start_line - 1 : end_line])
