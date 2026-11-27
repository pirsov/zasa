"""Базовые проверки контрактов Pydantic."""

import pytest
from pydantic import ValidationError

from agent.schema import ActionType, EditCommand, Plan, PlanStep


def test_valid_edit_command_parses() -> None:
    command = EditCommand(
        action=ActionType.replace_symbol,
        path="agent/schema.py",
        symbol="EditCommand",
        new_code="class EditCommand:\n    pass\n",
        reason="обновить модель",
    )
    assert command.action is ActionType.replace_symbol
    assert command.path == "agent/schema.py"
    assert command.symbol == "EditCommand"
    assert command.new_code == "class EditCommand:\n    pass\n"


def test_replace_symbol_without_new_code_fails() -> None:
    with pytest.raises(ValidationError):
        EditCommand(
            action=ActionType.replace_symbol,
            path="agent/schema.py",
            symbol="EditCommand",
            reason="нет нового кода",
        )


def test_path_with_parent_segment_fails() -> None:
    with pytest.raises(ValidationError):
        EditCommand(
            action=ActionType.read_symbol,
            path="../secrets.env",
            symbol="TOKEN",
            reason="чтение вне проекта",
        )


def test_plan_with_eight_steps_fails() -> None:
    steps = [
        PlanStep(id=index, action=ActionType.run_check) for index in range(1, 9)
    ]
    with pytest.raises(ValidationError):
        Plan(goal="слишком длинный план", steps=steps)


def test_plan_with_cycle_fails() -> None:
    steps = [
        PlanStep(id=1, action=ActionType.run_check, depends_on=[2]),
        PlanStep(id=2, action=ActionType.read_symbol, path="a.py", depends_on=[1]),
    ]
    with pytest.raises(ValidationError):
        Plan(goal="цикл", steps=steps)


def test_plan_with_valid_graph_passes() -> None:
    steps = [
        PlanStep(id=1, action=ActionType.read_symbol, path="agent/schema.py", symbol="Plan"),
        PlanStep(
            id=2,
            action=ActionType.replace_symbol,
            path="agent/schema.py",
            symbol="Plan",
            depends_on=[1],
            note="править после чтения",
        ),
        PlanStep(id=3, action=ActionType.run_check, depends_on=[2]),
    ]
    plan = Plan(goal="поправить Plan", assumptions=["репозиторий локальный"], steps=steps)
    assert [step.id for step in plan.steps] == [1, 2, 3]
    assert plan.steps[1].depends_on == [1]
    assert plan.needs_split is False
