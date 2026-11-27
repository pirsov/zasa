"""Pydantic-модели агента — единый источник правды."""

from __future__ import annotations

from collections import deque
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, field_validator, model_validator


class ActionType(str, Enum):
    replace_symbol = "replace_symbol"
    insert_after_symbol = "insert_after_symbol"
    write_file = "write_file"
    read_symbol = "read_symbol"
    run_check = "run_check"
    run_command = "run_command"
    call_mcp = "call_mcp"


_ACTIONS_REQUIRING_CODE = frozenset(
    {
        ActionType.replace_symbol,
        ActionType.insert_after_symbol,
        ActionType.write_file,
    }
)
_ACTIONS_REQUIRING_SYMBOL = frozenset(
    {
        ActionType.replace_symbol,
        ActionType.insert_after_symbol,
    }
)


class EditCommand(BaseModel):
    """Ответ исполнителя: одно изменение в кодовой базе."""

    action: ActionType
    path: str | None = None
    symbol: str | None = None
    new_code: str | None = None
    command: str | None = None
    mcp_server: str | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] | None = None
    reason: str

    @field_validator("path")
    @classmethod
    def path_must_be_relative(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.replace("\\", "/")
        if normalized.startswith("/"):
            raise ValueError("path must be relative and must not start with '/'")
        if ".." in normalized.split("/"):
            raise ValueError("path must not contain '..'")
        return value

    @model_validator(mode="after")
    def require_fields_for_action(self) -> EditCommand:
        if self.action != ActionType.run_check and not self.path:
            raise ValueError("path is required unless action is run_check")
        if self.action in _ACTIONS_REQUIRING_CODE and not self.new_code:
            raise ValueError(
                "new_code is required and must be non-empty when action is "
                "replace_symbol, insert_after_symbol, or write_file"
            )
        if self.action in _ACTIONS_REQUIRING_SYMBOL and not self.symbol:
            raise ValueError(
                "symbol is required when action is "
                "replace_symbol or insert_after_symbol"
            )
        if self.action == ActionType.run_command:
            if self.command is None or not self.command.strip():
                raise ValueError("command is required when action is run_command")
        elif self.command is not None:
            raise ValueError("command must be None unless action is run_command")
        if self.action == ActionType.call_mcp:
            if self.mcp_server is None or not self.mcp_server.strip():
                raise ValueError("mcp_server is required when action is call_mcp")
            if self.tool_name is None or not self.tool_name.strip():
                raise ValueError("tool_name is required when action is call_mcp")
        elif self.mcp_server is not None or self.tool_name is not None or self.tool_arguments is not None:
            raise ValueError(
                "mcp_server, tool_name, and tool_arguments must be None unless action is call_mcp"
            )
        return self


class PlanStep(BaseModel):
    id: int
    action: ActionType
    path: str | None = None
    symbol: str | None = None
    depends_on: list[int] = []
    note: str = ""


class Plan(BaseModel):
    goal: str
    assumptions: list[str] = []
    steps: list[PlanStep]
    risks: list[str] = []
    needs_split: bool = False

    @model_validator(mode="after")
    def validate_steps(self) -> Plan:
        count = len(self.steps)
        if count < 1 or count > 7:
            raise ValueError("steps must contain from 1 to 7 items")

        ids = [step.id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("step ids must be unique")

        known = set(ids)
        children: dict[int, list[int]] = {step_id: [] for step_id in ids}
        indegree = {step_id: 0 for step_id in ids}
        for step in self.steps:
            for dep in step.depends_on:
                if dep not in known:
                    raise ValueError(
                        f"depends_on references unknown step id {dep}"
                    )
                children[dep].append(step.id)
                indegree[step.id] += 1

        queue: deque[int] = deque(
            step_id for step_id, degree in indegree.items() if degree == 0
        )
        visited = 0
        while queue:
            current = queue.popleft()
            visited += 1
            for child in children[current]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)

        if visited != len(ids):
            raise ValueError("depends_on contains a cycle")
        return self


class ReplanOp(BaseModel):
    operation: Literal["insert_before", "replace_step", "drop_step"]
    target_step_id: int
    new_steps: list[PlanStep] = []
    reason: str


class ValidatorError(BaseModel):
    level: Literal["L1", "L2", "L3", "L4"]
    message: str
    hint: str = ""


def edit_command_json_schema() -> dict[str, Any]:
    return EditCommand.model_json_schema()


def plan_json_schema() -> dict[str, Any]:
    return Plan.model_json_schema()


def replan_json_schema() -> dict[str, Any]:
    return ReplanOp.model_json_schema()
