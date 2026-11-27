"""Репланнер: правит план, если шаг не прошёл за все попытки."""

from __future__ import annotations

import json

import httpx
from pydantic import ValidationError

from agent.config import Settings, get_settings
from agent.prompts import REPLANNER_SYSTEM_PROMPT
from agent.schema import Plan, PlanStep, ReplanOp, ValidatorError, replan_json_schema

_MAX_ATTEMPTS = 3


class ReplanGenerationError(RuntimeError):
    """Модель не вернула валидный ReplanOp за отведённые попытки."""


class Replanner:
    """Запрашивает у Ollama одну операцию правки плана."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def replan(
        self,
        plan: Plan,
        failed_step: PlanStep,
        error: ValidatorError,
    ) -> ReplanOp:
        system_prompt = _render_system_prompt(plan, failed_step, error)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Output the ReplanOp JSON."},
        ]
        url = f"{self._settings.ollama_base_url.rstrip('/')}/api/chat"
        last_error = "модель не вернула операцию"

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
                    return ReplanOp.model_validate_json(content)
                except ValidationError as exc:
                    last_error = str(exc)
                    messages.append({"role": "assistant", "content": content})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "The previous JSON does not match the ReplanOp schema. "
                                f"Validation error:\n{last_error}\n"
                                "Fix the JSON and output ONLY a valid JSON object."
                            ),
                        }
                    )

        raise ReplanGenerationError(
            f"Не удалось получить валидную операцию за {_MAX_ATTEMPTS} попытки. "
            f"Последняя ошибка: {last_error}"
        )


def _render_system_prompt(plan: Plan, failed_step: PlanStep, error: ValidatorError) -> str:
    hint = f" {error.hint}" if error.hint else ""
    template = REPLANNER_SYSTEM_PROMPT.replace("{{", "{").replace("}}", "}")
    return template.format(
        replan_json_schema=json.dumps(replan_json_schema(), ensure_ascii=False, indent=2),
        plan_json=plan.model_dump_json(),
        failed_step_json=failed_step.model_dump_json(),
        error_message=f"{error.level}: {error.message}.{hint}",
    )
