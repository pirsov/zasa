"""Проверки извлечения символов через tree-sitter."""

from pathlib import Path

from agent.retriever import CodeRetriever

SAMPLE = """\
import os

def top_func(a, b):
    return a + b

class MyClass:
    def __init__(self):
        self.x = 1

    def method_one(self):
        print("hello")
        return True
"""


def _sample_path(tmp_path: Path) -> Path:
    path = tmp_path / "sample.py"
    path.write_text(SAMPLE, encoding="utf-8")
    return path


def test_get_outline(tmp_path: Path) -> None:
    outline = CodeRetriever().get_outline(str(_sample_path(tmp_path)))
    assert outline == [
        {"name": "top_func", "type": "function", "start_line": 3, "end_line": 4},
        {"name": "MyClass", "type": "class", "start_line": 6, "end_line": 12},
    ]


def test_get_symbol_function(tmp_path: Path) -> None:
    code = CodeRetriever().get_symbol(str(_sample_path(tmp_path)), "top_func")
    assert code == "def top_func(a, b):\n    return a + b"


def test_get_symbol_method(tmp_path: Path) -> None:
    code = CodeRetriever().get_symbol(str(_sample_path(tmp_path)), "method_one")
    assert code == (
        "    def method_one(self):\n"
        '        print("hello")\n'
        "        return True"
    )


def test_get_symbol_missing(tmp_path: Path) -> None:
    assert CodeRetriever().get_symbol(str(_sample_path(tmp_path)), "missing") is None


def test_get_signature(tmp_path: Path) -> None:
    snippet = CodeRetriever().get_signature_and_context(
        str(_sample_path(tmp_path)),
        "top_func",
        context_lines=1,
    )
    assert snippet == "def top_func(a, b):\n    return a + b"
