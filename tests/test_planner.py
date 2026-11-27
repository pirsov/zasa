"""Планировщик: успешный ответ Ollama, повтор и отказ."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

from agent.config import Settings
from agent.planner import PlanGenerationError, Planner
from agent.schema import ActionType, Plan, PlanStep

_CHAT_URL = "http://ollama.test/api/chat"

_VALID_PLAN = Plan(
    goal="добавить функцию",
    assumptions=["репозиторий локальный"],
    steps=[
        PlanStep(
            id=1,
            action=ActionType.read_symbol,
            path="agent/schema.py",
            symbol="Plan",
            note="посмотреть модель",
        ),
        PlanStep(
            id=2,
            action=ActionType.run_check,
            depends_on=[1],
            note="pytest",
        ),
    ],
    risks=["схема может измениться"],
).model_dump_json()

_INVALID_PLAN = json.dumps({"goal": "сломанный план"})


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


def test_create_plan_success() -> None:
    planner = Planner(_settings())
    with respx.mock:
        route = respx.post(_CHAT_URL).mock(return_value=_ollama(_VALID_PLAN))
        plan = asyncio.run(planner.create_plan("добавить функцию", repo_map="agent/schema.py"))

    assert route.call_count == 1
    assert isinstance(plan, Plan)
    assert plan.goal == "добавить функцию"
    assert [step.id for step in plan.steps] == [1, 2]

    payload = json.loads(route.calls[0].request.content)
    assert payload["format"] == "json"
    assert payload["model"] == "test-model"
    assert payload["messages"][1]["content"] == "добавить функцию"
    assert "добавить функцию" in payload["messages"][0]["content"]
    assert '"goal"' in payload["messages"][0]["content"]


def test_create_plan_puts_the_dialogue_next_to_the_new_phrase() -> None:
    planner = Planner(_settings())
    with respx.mock:
        route = respx.post(_CHAT_URL).mock(return_value=_ollama(_VALID_PLAN))
        asyncio.run(
            planner.create_plan(
                "Выдумай рандомный дом",
                memory_ctx="Человек: Азов\nАгент: Введите адрес",
            )
        )

    payload = json.loads(route.calls[0].request.content)
    text = payload["messages"][1]["content"]
    assert "Диалог:" in text
    assert "Человек: Азов" in text
    assert "Новая фраза: Выдумай рандомный дом" in text


def test_create_plan_retry() -> None:
    planner = Planner(_settings())
    with respx.mock:
        route = respx.post(_CHAT_URL).mock(
            side_effect=[
                _ollama(_INVALID_PLAN),
                _ollama(_VALID_PLAN),
            ]
        )
        plan = asyncio.run(planner.create_plan("починить план"))

    assert route.call_count == 2
    assert isinstance(plan, Plan)
    assert plan.goal == "добавить функцию"

    retry_payload = json.loads(route.calls[1].request.content)
    assert [message["role"] for message in retry_payload["messages"]] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert "Ошибка проверки" in retry_payload["messages"][-1]["content"]


def test_create_plan_failure() -> None:
    planner = Planner(_settings())
    with respx.mock:
        route = respx.post(_CHAT_URL).mock(
            side_effect=[_ollama(_INVALID_PLAN) for _ in range(3)]
        )
        with pytest.raises(PlanGenerationError):
            asyncio.run(planner.create_plan("снова сломанный план"))

    assert route.call_count == 3
