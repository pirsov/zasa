"""Исполнитель: валидная команда, прошлая ошибка и повтор при битом JSON."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

from agent.config import Settings
from agent.executor import EditCommandGenerationError, Executor
from agent.schema import ActionType, EditCommand, PlanStep, ValidatorError

_CHAT_URL = "http://ollama.test/api/chat"

_STEP = PlanStep(
    id=1,
    action=ActionType.replace_symbol,
    path="agent/example.py",
    symbol="example",
    note="заменить функцию",
)

_VALID_COMMAND = EditCommand(
    action=ActionType.replace_symbol,
    path="agent/example.py",
    symbol="example",
    new_code="def example():\n    return 1\n",
    reason="заменить example",
).model_dump_json()

_INVALID_COMMAND = json.dumps(
    {
        "action": "replace_symbol",
        "symbol": "example",
        "new_code": "def example():\n    pass\n",
        "reason": "нет пути",
    }
)


def _settings() -> Settings:
    return Settings(
        ollama_base_url="http://ollama.test",
        ollama_model="test-model",
    )


def _ollama(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "test-model",
            "message": {"role": "assistant", "content": content},
            "done": True,
        },
    )


def test_execute_success() -> None:
    executor = Executor(_settings())
    with respx.mock:
        route = respx.post(_CHAT_URL).mock(return_value=_ollama(_VALID_COMMAND))
        command = asyncio.run(
            executor.generate_edit_command(
                "заменить example",
                _STEP,
                "def example(): pass",
            )
        )

    assert route.call_count == 1
    assert isinstance(command, EditCommand)
    assert command.action is ActionType.replace_symbol
    assert command.path == "agent/example.py"
    assert command.symbol == "example"

    payload = json.loads(route.calls[0].request.content)
    assert payload["format"] == "json"
    assert payload["model"] == "test-model"


def test_execute_with_previous_error() -> None:
    executor = Executor(_settings())
    error = ValidatorError(
        level="L2",
        message="символ не найден",
        hint="проверь имя",
    )
    with respx.mock:
        route = respx.post(_CHAT_URL).mock(return_value=_ollama(_VALID_COMMAND))
        command = asyncio.run(
            executor.generate_edit_command(
                "заменить example",
                _STEP,
                "def example(): pass",
                previous_error=error,
            )
        )

    assert isinstance(command, EditCommand)
    payload = json.loads(route.calls[0].request.content)
    system_prompt = payload["messages"][0]["content"]
    assert (
        "PREVIOUS ATTEMPT FAILED WITH ERROR: L2 - символ не найден. HINT: проверь имя"
        in system_prompt
    )


def test_execute_invalid_json() -> None:
    executor = Executor(_settings())
    with respx.mock:
        route = respx.post(_CHAT_URL).mock(return_value=_ollama(_INVALID_COMMAND))
        with pytest.raises(EditCommandGenerationError):
            asyncio.run(
                executor.generate_edit_command(
                    "заменить example",
                    _STEP,
                    "def example(): pass",
                )
            )

    assert route.call_count == 3
    retry = json.loads(route.calls[1].request.content)
    assert retry["format"] == "json"
    assert "Validation error" in retry["messages"][-1]["content"]
    assert "path" in retry["messages"][-1]["content"]
