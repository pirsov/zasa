"""CLI планировщика: задача из argv, JSON-план в stdout."""

from __future__ import annotations

import asyncio
import sys

import httpx
from rich import print_json
from rich.console import Console

from agent.planner import PlanGenerationError, Planner

_stderr = Console(stderr=True)


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        _stderr.print('Укажите задачу: python -m agent.main "что сделать"')
        raise SystemExit(1)

    task = sys.argv[1]
    try:
        plan = asyncio.run(Planner().create_plan(task))
    except PlanGenerationError as exc:
        _stderr.print(f"Не удалось построить план: {exc}")
        raise SystemExit(1) from exc
    except httpx.HTTPError as exc:
        _stderr.print(f"Не удалось обратиться к Ollama: {exc}")
        raise SystemExit(1) from exc

    print_json(plan.model_dump_json())


if __name__ == "__main__":
    main()
