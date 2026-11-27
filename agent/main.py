"""CLI: план по задаче, либо команда исполнителя для первого шага."""

from __future__ import annotations

import asyncio
import sys

import httpx
from rich import print_json
from rich.console import Console

from agent.executor import EditCommandGenerationError, Executor
from agent.planner import PlanGenerationError, Planner
from agent.schema import EditCommand

_stderr = Console(stderr=True)
_FAKE_STEP_CONTEXT = "def example(): pass"


def main() -> None:
    task, execute = _parse_args(sys.argv[1:])
    try:
        if execute:
            command = asyncio.run(_execute_first_step(task))
            print_json(command.model_dump_json())
            return
        plan = asyncio.run(Planner().create_plan(task))
    except PlanGenerationError as exc:
        _stderr.print(f"Не удалось построить план: {exc}")
        raise SystemExit(1) from exc
    except EditCommandGenerationError as exc:
        _stderr.print(f"Не удалось получить команду: {exc}")
        raise SystemExit(1) from exc
    except httpx.HTTPError as exc:
        _stderr.print(f"Не удалось обратиться к Ollama: {exc}")
        raise SystemExit(1) from exc

    print_json(plan.model_dump_json())


def _parse_args(argv: list[str]) -> tuple[str, bool]:
    execute = "--exec" in argv
    positional = [arg for arg in argv if arg != "--exec"]
    if not positional or not positional[0].strip():
        _stderr.print('Укажите задачу: python -m agent.main "что сделать" [--exec]')
        raise SystemExit(1)
    if len(positional) > 1:
        execute = True
    return positional[0], execute


async def _execute_first_step(task: str) -> EditCommand:
    plan = await Planner().create_plan(task)
    step = plan.steps[0]
    return await Executor().generate_edit_command(
        plan.goal,
        step,
        _FAKE_STEP_CONTEXT,
    )


if __name__ == "__main__":
    main()
