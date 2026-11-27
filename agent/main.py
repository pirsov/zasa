"""CLI агента: задача из аргументов, полный цикл оркестратора."""

from __future__ import annotations

import asyncio
import sys

import httpx
from rich.console import Console

from agent.executor import EditCommandGenerationError
from agent.orchestrator import Orchestrator, OrchestratorError
from agent.planner import PlanGenerationError

_stderr = Console(stderr=True)


def main() -> None:
    task = _parse_task(sys.argv[1:])
    try:
        asyncio.run(Orchestrator().run(task))
    except KeyboardInterrupt:
        _stderr.print("Остановлено. План прерван.")
        raise SystemExit(130) from None
    except OrchestratorError as exc:
        raise SystemExit(1) from exc
    except PlanGenerationError as exc:
        _stderr.print(f"Не удалось построить план: {exc}")
        raise SystemExit(1) from exc
    except EditCommandGenerationError as exc:
        _stderr.print(f"Не удалось получить команду: {exc}")
        raise SystemExit(1) from exc
    except httpx.HTTPError as exc:
        _stderr.print(f"Не удалось обратиться к Ollama: {exc}")
        raise SystemExit(1) from exc


def _parse_task(argv: list[str]) -> str:
    if not argv:
        _usage()
    if argv[0] in {"-t", "--task"}:
        if len(argv) < 2 or not argv[1].strip():
            _usage()
        return argv[1]
    if argv[0].startswith("-"):
        _usage()
    if not argv[0].strip():
        _usage()
    return argv[0]


def _usage() -> None:
    _stderr.print('Укажите задачу: python -m agent.main "что сделать"')
    _stderr.print('или: python -m agent.main -t "что сделать"')
    raise SystemExit(1)


if __name__ == "__main__":
    main()
