"""Оркестратор: план, исполнение шагов, проверка и запись на диск."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from rich.console import Console

from agent.config import Settings, get_settings
from agent.executor import EditCommandGenerationError, Executor
from agent.household import Household
from agent.mcp_client import McpClient, McpClientError
from agent.memory import MemoryManager
from agent.outcomes import Outcomes
from agent.planner import Planner
from agent.replanner import Replanner
from agent.retriever import CodeRetriever
from agent.schema import ActionType, EditCommand, Plan, PlanStep, ReplanOp, ValidatorError
from agent.tool_runner import ToolRunner
from agent.validator import Applier, Validator

_MAX_REPLANS = 3

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
        self.mcp = McpClient()
        self.memory = MemoryManager("plans/memory.json")
        self.household = Household("home", self.memory, self.tool_runner)
        self.outcomes = Outcomes()
        self.replanner = Replanner(self._settings)

    async def run(self, task: str) -> None:
        try:
            answer = await self.household.handle(task)
            if answer is None:
                answer = self.outcomes.achieve(task)
            if answer is not None:
                self._console.print(answer)
                self.memory.save_fact(f"Успешно выполнена задача: {task}")
                return
            memory_ctx = self.memory.get_context()
            servers = ", ".join(self.mcp.load_config().mcp_servers)
            plan = await self.planner.create_plan(
                task,
                mcp_servers=servers,
                memory_ctx=memory_ctx,
            )
            self._save_plan(plan)
            self._print_plan(plan)
            await self._run_steps(plan)
            self.memory.save_fact(f"Успешно выполнена задача: {task}")
        finally:
            await self.mcp.close()

    def _save_plan(self, plan: Plan) -> Path:
        directory = Path(self._settings.plans_dir)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        path = directory / f"plan_{stamp}.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(plan.model_dump(mode="json"), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        return path

    async def _run_steps(self, plan: Plan) -> None:
        index = 0
        done: set[int] = set()
        replans = 0
        while index < len(plan.steps):
            step = plan.steps[index]
            self._ensure_dependencies(step, done)
            context, previous_error = self._context_for(step)
            error = await self._execute_step(plan.goal, step, context, previous_error)
            if error is None:
                done.add(step.id)
                index += 1
                continue
            if replans >= _MAX_REPLANS:
                raise OrchestratorError(
                    f"Шаг {step.id} не выполнен, репланнер исчерпал попытки"
                )
            operation = await self.replanner.replan(plan, step, error)
            index = self._apply_replan(plan, index, operation)
            replans += 1
            self._console.print(
                "[yellow]План изменен Репланнером: "
                f"{operation.operation} шаг {operation.target_step_id}. "
                f"{operation.reason}[/yellow]"
            )
            self._print_plan(plan)

    def _apply_replan(self, plan: Plan, index: int, operation: ReplanOp) -> int:
        position = index
        for i, step in enumerate(plan.steps):
            if step.id == operation.target_step_id:
                position = i
                break
        if operation.operation == "drop_step":
            del plan.steps[position]
            return position
        if operation.operation == "replace_step":
            if operation.new_steps:
                plan.steps[position : position + 1] = list(operation.new_steps)
            else:
                del plan.steps[position]
            return position
        for offset, step in enumerate(operation.new_steps):
            plan.steps.insert(position + offset, step)
        return position

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
    ) -> ValidatorError | None:
        retries = self._settings.max_step_retries
        for attempt in range(1, retries + 1):
            try:
                command = await self.executor.generate_edit_command(
                    plan_goal,
                    step,
                    context,
                    previous_error,
                )
            except EditCommandGenerationError as exc:
                previous_error = ValidatorError(
                    level="L1",
                    message=str(exc),
                    hint="Return one EditCommand. path may be null only for run_check.",
                )
                self._console.print(
                    f"[red]Шаг {step.id}, попытка {attempt}/{retries}: {previous_error.message}[/red]"
                )
                continue
            success, error = await self.validator.validate(command)
            if success and (
                step.action == ActionType.call_mcp or command.action == ActionType.call_mcp
            ):
                finished, previous_error = await self._call_mcp(step, command, attempt, retries)
                if finished:
                    return
                continue
            if success and (
                step.action == ActionType.run_command
                or command.action == ActionType.run_command
            ):
                finished, previous_error = await self._run_shell(step, command, attempt, retries)
                if finished:
                    return
                continue
            if success and command.action == ActionType.run_check and not command.path:
                self._console.print(f"[green]Шаг {step.id} выполнен: run_check[/green]")
                return
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
            f"[bold red]Шаг {step.id} не выполнен за {retries} попыток.[/bold red]"
        )
        return previous_error or ValidatorError(
            level="L2",
            message=f"Шаг {step.id} не выполнен за {retries} попыток",
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

    async def _call_mcp(
        self,
        step: PlanStep,
        command: EditCommand,
        attempt: int,
        retries: int,
    ) -> tuple[bool, ValidatorError | None]:
        server = command.mcp_server or ""
        tool = command.tool_name or ""
        try:
            text = await self.mcp.call_tool(server, tool, command.tool_arguments)
        except McpClientError as exc:
            error = ValidatorError(
                level="L2",
                message=str(exc),
                hint="Fix the MCP server, tool name, or arguments",
            )
            self._console.print(
                f"[red]Шаг {step.id}, попытка {attempt}/{retries}: {error.message}[/red]"
            )
            return False, error
        if text:
            self._console.print(text, style="green")
        self._console.print(f"[green]Шаг {step.id} выполнен: {server}/{tool}[/green]")
        return True, None

    def _print_streams(self, returncode: int, stdout: str, stderr: str) -> None:
        style = "green" if returncode == 0 else "red"
        if stdout:
            self._console.print(stdout, style=style, end="" if stdout.endswith("\n") else "\n")
        if stderr:
            self._console.print(stderr, style="red", end="" if stderr.endswith("\n") else "\n")
