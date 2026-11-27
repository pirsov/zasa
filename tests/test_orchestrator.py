"""Цикл оркестратора: успех, повтор шага и останов после лимита."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.config import Settings
from agent.memory import MemoryManager
from agent.orchestrator import Orchestrator, OrchestratorError
from agent.schema import ActionType, EditCommand, Plan, PlanStep, ReplanOp, ValidatorError

_COMMAND = EditCommand(
    action=ActionType.read_symbol,
    path="a.py",
    symbol="foo",
    reason="прочитать foo",
)

_ERROR = ValidatorError(level="L3", message="синтаксис сломан", hint="верни двоеточие")


def _settings(tmp_path: Path, retries: int = 3) -> Settings:
    return Settings(
        ollama_base_url="http://ollama.test",
        ollama_model="test-model",
        plans_dir=str(tmp_path / "plans"),
        logs_dir=str(tmp_path / "logs"),
        max_step_retries=retries,
    )


def _plan() -> Plan:
    return Plan(
        goal="сделать два шага",
        steps=[
            PlanStep(
                id=1,
                action=ActionType.read_symbol,
                path="a.py",
                symbol="foo",
            ),
            PlanStep(
                id=2,
                action=ActionType.run_check,
                depends_on=[1],
                note="pytest",
            ),
        ],
    )


def _orchestrator(tmp_path: Path, retries: int = 3) -> Orchestrator:
    orchestrator = Orchestrator(_settings(tmp_path, retries))
    orchestrator.retriever.get_symbol = MagicMock(return_value="def foo():\n    return 1\n")
    orchestrator.planner.create_plan = AsyncMock(return_value=_plan())
    orchestrator.executor.generate_edit_command = AsyncMock(return_value=_COMMAND)
    orchestrator.applier.apply = MagicMock()
    orchestrator.memory = MemoryManager(tmp_path / "plans" / "memory.json")
    orchestrator.replanner.replan = AsyncMock(side_effect=OrchestratorError("replan failed"))
    return orchestrator


@pytest.mark.asyncio
async def test_run_success_flow(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    orchestrator.validator.validate = AsyncMock(return_value=(True, None))

    await orchestrator.run("сделать два шага")

    assert orchestrator.applier.apply.call_count == 2
    saved = list(Path(orchestrator._settings.plans_dir).glob("plan_*.json"))
    assert len(saved) == 1
    payload = json.loads(saved[0].read_text(encoding="utf-8"))
    assert payload["goal"] == "сделать два шага"
    assert [step["id"] for step in payload["steps"]] == [1, 2]


@pytest.mark.asyncio
async def test_run_retry_logic(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    orchestrator.planner.create_plan = AsyncMock(
        return_value=Plan(
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
    )
    orchestrator.validator.validate = AsyncMock(
        side_effect=[(False, _ERROR), (True, None)]
    )

    await orchestrator.run("починить шаг")

    generate = orchestrator.executor.generate_edit_command
    assert generate.await_count == 2
    assert generate.await_args_list[0].args[3] is None
    assert generate.await_args_list[1].args[3] == _ERROR
    assert orchestrator.applier.apply.call_count == 1


@pytest.mark.asyncio
async def test_run_fail_after_max_retries(tmp_path: Path) -> None:
    retries = 3
    orchestrator = _orchestrator(tmp_path, retries)
    orchestrator.validator.validate = AsyncMock(return_value=(False, _ERROR))

    with pytest.raises(OrchestratorError):
        await orchestrator.run("сделать два шага")

    assert orchestrator.executor.generate_edit_command.await_count == retries
    assert orchestrator.applier.apply.call_count == 0


@pytest.mark.asyncio
async def test_replan_on_failure(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path, retries=2)
    orchestrator.planner.create_plan = AsyncMock(
        return_value=Plan(
            goal="один шаг",
            steps=[
                PlanStep(
                    id=1,
                    action=ActionType.read_symbol,
                    path="a.py",
                    symbol="foo",
                )
            ],
        )
    )
    orchestrator.validator.validate = AsyncMock(return_value=(False, _ERROR))
    orchestrator.replanner.replan = AsyncMock(
        return_value=ReplanOp(
            operation="drop_step",
            target_step_id=1,
            reason="шаг невозможно выполнить",
        )
    )

    await orchestrator.run("один шаг")

    orchestrator.replanner.replan.assert_awaited()
    failed_step = orchestrator.replanner.replan.await_args.args[1]
    assert failed_step.id == 1
    assert orchestrator.replanner.replan.await_args.args[2] == _ERROR
    assert orchestrator.applier.apply.call_count == 0
