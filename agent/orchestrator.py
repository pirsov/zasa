"""Оркестратор: план, исполнение шагов, проверка и запись на диск."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from rich.console import Console

from agent.config import Settings, get_settings
from agent.executor import Executor
from agent.planner import Planner
from agent.retriever import CodeRetriever
from agent.schema import ActionType, EditCommand, Plan, PlanStep, ValidatorError
from agent.tool_runner import ToolRunner
from agent.validator import Applier, Validator

_SYMBOL_ACTIONS = frozenset(
    {
        ActionType.replace_symbol,
        ActionType.read_symbol,
        ActionType.insert_after_symbol,
    }
)


class OrchestratorError(RuntimeError):
    """План остановлен: шаг не выполнен или зависимость не готова."""


class Orchestrator:
    """Связывает планировщик, исполнитель, валидатор и применение правок."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._console = Console()
        self.retriever = CodeRetriever()
        self.planner = Planner(self._settings)
        self.executor = Executor(self._settings)
        self.validator = Validator(self.retriever)
        self.applier = Applier(self.retriever)
        self.tool_runner = ToolRunner()

    async def run(self, task: str) -> None:
        plan = await self.planner.create_plan(task)
        self._save_plan(plan)
        self._print_plan(plan)

        done: set[int] = set()
        for step in plan.steps:
            self._ensure_dependencies(step, done)
            context, previous_error = self._context_for(step)
            await self._execute_step(plan.goal, step, context, previous_error)
            done.add(step.id)

    def _save_plan(self, plan: Plan) -> Path:
        directory = Path(self._settings.plans_dir)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        path = directory / f"plan_{stamp}.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(plan.model_dump(mode="json"), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        return path

    def _print_plan(self, plan: Plan) -> None:
        self._console.print(f"[bold]План:[/bold] {plan.goal}")
        self._console.print_json(data=plan.model_dump(mode="json"))

    def _ensure_dependencies(self, step: PlanStep, done: set[int]) -> None:
        pending = [dep for dep in step.depends_on if dep not in done]
        if pending:
            raise OrchestratorError(
                f"Шаг {step.id} зависит от невыполненных шагов: {pending}"
            )

    def _context_for(self, step: PlanStep) -> tuple[str, ValidatorError | None]:
        if step.action == ActionType.write_file:
            return "", None
        if step.action in _SYMBOL_ACTIONS and step.path and step.symbol:
            try:
                found = self.retriever.get_symbol(step.path, step.symbol)
            except FileNotFoundError:
                found = None
            if not found:
                return "", ValidatorError(
                    level="L2",
                    message="Symbol not found in file",
                )
            return found, None
        return "", None

    async def _execute_step(
        self,
        plan_goal: str,
        step: PlanStep,
        context: str,
        previous_error: ValidatorError | None,
    ) -> None:
        retries = self._settings.max_step_retries
        for attempt in range(1, retries + 1):
            command = await self.executor.generate_edit_command(
                plan_goal,
                step,
                context,
                previous_error,
            )
            success, error = await self.validator.validate(command)
            if success and (
                step.action == ActionType.run_command
                or command.action == ActionType.run_command
            ):
                finished, previous_error = await self._run_shell(step, command, attempt, retries)
                if finished:
                    return
                continue
            if success:
                self.applier.apply(command)
                self._console.print(
                    f"[green]Шаг {step.id} выполнен: {command.action.value} {command.path}[/green]"
                )
                return
            previous_error = error
            message = error.message if error is not None else "неизвестная ошибка"
            self._console.print(
                f"[red]Шаг {step.id}, попытка {attempt}/{retries}: {message}[/red]"
            )

        self._console.print(
            f"[bold red]Шаг {step.id} не выполнен за {retries} попыток. "
            "Выполнение плана остановлено.[/bold red]"
        )
        raise OrchestratorError(
            f"Шаг {step.id} не выполнен за {retries} попыток"
        )

    async def _run_shell(
        self,
        step: PlanStep,
        command: EditCommand,
        attempt: int,
        retries: int,
    ) -> tuple[bool, ValidatorError | None]:
        shell = command.command or ""
        if not shell.strip():
            error = ValidatorError(
                level="L1",
                message="command is required for run_command",
                hint="Put the shell command in the command field",
            )
            self._console.print(
                f"[red]Шаг {step.id}, попытка {attempt}/{retries}: {error.message}[/red]"
            )
            return False, error

        returncode, stdout, stderr = await self.tool_runner.execute(shell)
        self._print_streams(returncode, stdout, stderr)
        if returncode == 0:
            self._console.print(f"[green]Шаг {step.id} выполнен: {shell}[/green]")
            return True, None

        detail = stderr.strip() or stdout.strip() or "команда завершилась с ошибкой"
        error = ValidatorError(
            level="L2",
            message=f"Command exited with code {returncode}: {detail}",
            hint="Change the shell command and retry",
        )
        self._console.print(
            f"[red]Шаг {step.id}, попытка {attempt}/{retries}: {error.message}[/red]"
        )
        return False, error

    def _print_streams(self, returncode: int, stdout: str, stderr: str) -> None:
        style = "green" if returncode == 0 else "red"
        if stdout:
            self._console.print(stdout, style=style, end="" if stdout.endswith("\n") else "\n")
        if stderr:
            self._console.print(stderr, style="red", end="" if stderr.endswith("\n") else "\n")
