"""Планировщик: строит Plan через локальную модель Ollama."""

from __future__ import annotations

import json

import httpx
from pydantic import ValidationError

from agent.config import Settings, get_settings
from agent.prompts import PLANNER_SYSTEM_PROMPT
from agent.schema import Plan, plan_json_schema

_MAX_ATTEMPTS = 3


class PlanGenerationError(RuntimeError):
    """Модель не вернула валидный Plan за отведённые попытки."""


class Planner:
    """Запрашивает у Ollama JSON-план и проверяет его схемой Plan."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def create_plan(self, task: str, repo_map: str = "") -> Plan:
        system_prompt = _render_system_prompt(task, repo_map)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]
        url = f"{self._settings.ollama_base_url.rstrip('/')}/api/chat"
        last_error = "модель не вернула план"

        async with httpx.AsyncClient(timeout=120.0) as client:
            for _attempt in range(_MAX_ATTEMPTS):
                response = await client.post(
                    url,
                    json={
                        "model": self._settings.ollama_model,
                        "messages": messages,
                        "format": "json",
                        "stream": False,
                    },
                )
                response.raise_for_status()
                content = str(response.json()["message"]["content"])
                try:
                    return Plan.model_validate_json(content)
                except ValidationError as exc:
                    last_error = str(exc)
                    messages.append({"role": "assistant", "content": content})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "The previous JSON does not match the Plan schema. "
                                f"Validation error:\n{last_error}\n"
                                "Fix the JSON and output ONLY a valid JSON object."
                            ),
                        }
                    )

        raise PlanGenerationError(
            f"Не удалось получить валидный план за {_MAX_ATTEMPTS} попытки. "
            f"Последняя ошибка: {last_error}"
        )


def _render_system_prompt(task: str, repo_map: str) -> str:
    schema = json.dumps(plan_json_schema(), ensure_ascii=False, indent=2)
    template = PLANNER_SYSTEM_PROMPT.replace("{{", "{").replace("}}", "}")
    return template.format(
        plan_json_schema=schema,
        task=task,
        repo_map=repo_map,
    )
