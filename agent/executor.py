"""Исполнитель: по одному шагу плана получает EditCommand от Ollama."""

from __future__ import annotations

import json

import httpx
from pydantic import ValidationError

from agent.config import Settings, get_settings
from agent.prompts import EXECUTOR_SYSTEM_PROMPT
from agent.schema import EditCommand, PlanStep, ValidatorError, edit_command_json_schema

_MAX_ATTEMPTS = 3  # первая попытка и до 2 ретраев


class EditCommandGenerationError(RuntimeError):
    """Модель не вернула валидный EditCommand за отведённые попытки."""


class Executor:
    """Запрашивает у Ollama одну команду изменения и проверяет её схемой."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def generate_edit_command(
        self,
        plan_goal: str,
        step: PlanStep,
        step_context: str,
        previous_error: ValidatorError | None = None,
    ) -> EditCommand:
        previous_error_text = _previous_error_text(previous_error)
        system_prompt = _render_system_prompt(
            plan_goal=plan_goal,
            step_json=step.model_dump_json(),
            step_context=step_context,
            previous_error_text=previous_error_text,
        )
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Output the EditCommand JSON for the current step."},
        ]
        url = f"{self._settings.ollama_base_url.rstrip('/')}/api/chat"
        last_error = "модель не вернула команду"

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
                    return EditCommand.model_validate_json(content)
                except ValidationError as exc:
                    last_error = str(exc)
                    messages.append({"role": "assistant", "content": content})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Прошлый JSON не совпал со схемой EditCommand. "
                                f"Ошибка проверки:\n{last_error}\n"
                                "Исправь JSON и выведи только корректный JSON-объект."
                            ),
                        }
                    )

        raise EditCommandGenerationError(
            f"Не удалось получить валидную команду за {_MAX_ATTEMPTS} попытки. "
            f"Последняя ошибка: {last_error}"
        )


def _previous_error_text(previous_error: ValidatorError | None) -> str:
    if previous_error is None:
        return ""
    return (
        "Прошлая попытка не удалась: "
        f"{previous_error.level} — {previous_error.message}. Подсказка: {previous_error.hint}"
    )


def _render_system_prompt(
    *,
    plan_goal: str,
    step_json: str,
    step_context: str,
    previous_error_text: str,
) -> str:
    schema = json.dumps(edit_command_json_schema(), ensure_ascii=False, indent=2)
    template = EXECUTOR_SYSTEM_PROMPT.replace("{{", "{").replace("}}", "}")
    return template.format(
        edit_command_schema=schema,
        plan_goal=plan_goal,
        step_json=step_json,
        step_context=step_context,
        previous_error_text=previous_error_text,
    )
