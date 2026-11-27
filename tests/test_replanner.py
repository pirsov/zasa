"""Репланнер: JSON от Ollama становится ReplanOp."""

from __future__ import annotations

import asyncio
import json

import httpx
import respx

from agent.config import Settings
from agent.replanner import Replanner
from agent.schema import ActionType, Plan, PlanStep, ReplanOp, ValidatorError

_CHAT_URL = "http://ollama.test/api/chat"

_PLAN = Plan(
    goal="починить шаг",
    steps=[
        PlanStep(
            id=1,
            action=ActionType.read_symbol,
            path="a.py",
            symbol="foo",
        )
    ],
)

_STEP = _PLAN.steps[0]
_ERROR = ValidatorError(level="L3", message="синтаксис сломан", hint="верни двоеточие")

_VALID_OP = ReplanOp(
    operation="insert_before",
    target_step_id=1,
    new_steps=[
        PlanStep(
            id=2,
            action=ActionType.read_symbol,
            path="a.py",
            symbol="foo",
            note="сначала прочитать файл",
        )
    ],
    reason="шаг падает без контекста",
).model_dump_json()


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


def test_replan_returns_op() -> None:
    replanner = Replanner(_settings())
    with respx.mock:
        route = respx.post(_CHAT_URL).mock(return_value=_ollama(_VALID_OP))
        operation = asyncio.run(replanner.replan(_PLAN, _STEP, _ERROR))

    assert route.call_count == 1
    assert isinstance(operation, ReplanOp)
    assert operation.operation == "insert_before"
    assert operation.target_step_id == 1
    assert operation.new_steps[0].id == 2

    payload = json.loads(route.calls[0].request.content)
    assert payload["format"] == "json"
    assert payload["model"] == "test-model"
    prompt = payload["messages"][0]["content"]
    assert "синтаксис сломан" in prompt
    assert '"operation"' in prompt
