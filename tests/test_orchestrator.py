"""Цикл оркестратора: успех, повтор шага и останов после лимита."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.config import Settings
from agent.executor import EditCommandGenerationError
from agent.hands import Hands
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
    orchestrator.hands = Hands(tmp_path / "home")
    orchestrator.replanner.replan = AsyncMock(side_effect=OrchestratorError("replan failed"))
    return orchestrator


@pytest.mark.asyncio
async def test_every_request_goes_to_the_planner(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    orchestrator.validator.validate = AsyncMock(return_value=(True, None))
    await orchestrator.run("запомни купить молоко")
    orchestrator.planner.create_plan.assert_awaited()
    assert orchestrator.planner.create_plan.await_args.args[0] == "запомни купить молоко"


@pytest.mark.asyncio
async def test_agent_runs_the_tool_it_chose(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    orchestrator.hands = Hands(tmp_path / "home")
    orchestrator.planner.create_plan = AsyncMock(
        return_value=Plan(
            goal="узнать город",
            steps=[PlanStep(id=1, action=ActionType.call_mcp, note="спросить")],
        )
    )
    orchestrator.executor.generate_edit_command = AsyncMock(
        return_value=EditCommand(
            action=ActionType.call_mcp,
            path=".",
            mcp_server="hands",
            tool_name="ask",
            tool_arguments={"text": "В каком городе доставить?"},
            reason="город не назван",
        )
    )
    await orchestrator.run("я хочу пиццу")
    orchestrator.planner.create_plan.assert_awaited()
    facts = orchestrator.memory.load()
    assert "Человек: я хочу пиццу" in facts
    assert "Агент: В каком городе доставить?" in facts


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
async def test_stuck_step_asks_instead_of_stopping(tmp_path: Path) -> None:
    retries = 3
    orchestrator = _orchestrator(tmp_path, retries)
    orchestrator.validator.validate = AsyncMock(return_value=(False, _ERROR))

    await orchestrator.run("сделать два шага")

    assert orchestrator.executor.generate_edit_command.await_count == retries
    assert orchestrator.applier.apply.call_count == 0
    assert any("Агент:" in fact and "ограничение" in fact for fact in orchestrator.memory.load())
    assert not any(fact.startswith("Успешно") for fact in orchestrator.memory.load())


@pytest.mark.asyncio
async def test_unfinished_plan_continues(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    orchestrator.validator.validate = AsyncMock(return_value=(True, None))
    orchestrator.executor.generate_edit_command = AsyncMock(
        return_value=EditCommand(
            action=ActionType.run_check,
            reason="проверка",
        )
    )
    orchestrator.planner.create_plan = AsyncMock(
        side_effect=[
            Plan(
                goal="часть",
                needs_split=True,
                steps=[PlanStep(id=1, action=ActionType.run_check, note="первая часть")],
            ),
            Plan(
                goal="остаток",
                steps=[PlanStep(id=1, action=ActionType.run_check, note="конец")],
            ),
        ]
    )

    await orchestrator.run("большая задача")

    assert orchestrator.planner.create_plan.await_count == 2
    followup = orchestrator.planner.create_plan.await_args_list[1].kwargs["memory_ctx"]
    assert "первая часть" in followup
    assert "Продолжай до результата" in followup
    saved = list(Path(orchestrator._settings.plans_dir).glob("plan_*.json"))
    assert len(saved) == 2


@pytest.mark.asyncio
async def test_ask_stops_until_the_person_answers(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path)
    orchestrator.planner.create_plan = AsyncMock(
        return_value=Plan(
            goal="узнать адрес",
            needs_split=True,
            steps=[
                PlanStep(id=1, action=ActionType.call_mcp, note="спросить адрес"),
                PlanStep(id=2, action=ActionType.run_check, depends_on=[1], note="дальше"),
            ],
        )
    )
    orchestrator.executor.generate_edit_command = AsyncMock(
        return_value=EditCommand(
            action=ActionType.call_mcp,
            path=".",
            mcp_server="hands",
            tool_name="ask",
            tool_arguments={"text": "Какой адрес?"},
            reason="нет адреса",
        )
    )

    await orchestrator.run("довези пиццу")

    assert orchestrator.executor.generate_edit_command.await_count == 1
    assert orchestrator.planner.create_plan.await_count == 1
    facts = orchestrator.memory.load()
    assert "Агент: Какой адрес?" in facts
    assert not any(fact.startswith("Успешно") for fact in facts)


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


@pytest.mark.asyncio
async def test_generation_error_triggers_replan(tmp_path: Path) -> None:
    orchestrator = _orchestrator(tmp_path, retries=2)
    orchestrator.planner.create_plan = AsyncMock(
        return_value=Plan(
            goal="проверка",
            steps=[PlanStep(id=1, action=ActionType.run_check, note="pytest")],
        )
    )
    orchestrator.executor.generate_edit_command = AsyncMock(
        side_effect=EditCommandGenerationError("path is null")
    )
    orchestrator.replanner.replan = AsyncMock(
        return_value=ReplanOp(
            operation="drop_step",
            target_step_id=1,
            reason="проверку можно пропустить",
        )
    )

    await orchestrator.run("проверка")

    assert orchestrator.executor.generate_edit_command.await_count == 2
    orchestrator.replanner.replan.assert_awaited()
    assert orchestrator.applier.apply.call_count == 0
