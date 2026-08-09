"""Contracts for strict Responses API schemas."""

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from mempilot.agent.policies import AgentPolicy, FlowState
from mempilot.agent.schemas import ListProcessesArgs, strict_schema
from mempilot.agent.tools import ToolRegistry


class _ControllerStub:
    pass


class _NestedLeaf(BaseModel):
    value: str


class _NestedArgs(BaseModel):
    leaves: list[_NestedLeaf]


def _walk_objects(node: Any) -> None:
    if isinstance(node, dict):
        assert "default" not in node
        assert "title" not in node
        for keyword in {
            "allOf",
            "not",
            "if",
            "then",
            "else",
            "dependentRequired",
            "dependentSchemas",
        }:
            assert keyword not in node
        properties = node.get("properties")
        if node.get("type") == "object" or isinstance(properties, dict):
            object_properties = properties if isinstance(properties, dict) else {}
            assert node["additionalProperties"] is False
            assert node["required"] == list(object_properties)
        for value in node.values():
            _walk_objects(value)
    elif isinstance(node, list):
        for value in node:
            _walk_objects(value)


def test_every_tool_has_flat_strict_responses_schema() -> None:
    registry = ToolRegistry(_ControllerStub(), AgentPolicy())  # type: ignore[arg-type]

    specs = registry.specs()

    assert len(specs) == len(registry.tools)
    assert {spec["name"] for spec in specs} == {tool.name for tool in registry.tools}
    for spec in specs:
        assert spec["type"] == "function"
        assert spec["strict"] is True
        assert "function" not in spec
        _walk_objects(spec["parameters"])


def test_tool_specs_are_limited_to_actions_valid_for_current_flow() -> None:
    registry = ToolRegistry(_ControllerStub(), AgentPolicy())  # type: ignore[arg-type]

    no_process = {spec["name"] for spec in registry.specs(FlowState.NO_PROCESS)}
    narrowed = {spec["name"] for spec in registry.specs(FlowState.NARROWED)}

    assert "attach_process" in no_process
    assert "save_trainer_trick" not in no_process
    assert "attach_process" not in narrowed
    assert "save_trainer_trick" in narrowed
    assert len(narrowed) < len(registry.tools)


def test_every_tool_argument_model_rejects_unknown_fields() -> None:
    registry = ToolRegistry(_ControllerStub(), AgentPolicy())  # type: ignore[arg-type]

    for tool in registry.tools:
        with pytest.raises(ValidationError) as captured:
            tool.args_model.model_validate({"unexpected": True})
        assert any(error["type"] == "extra_forbidden" for error in captured.value.errors())


def test_optional_fields_are_still_required_by_strict_contract() -> None:
    with pytest.raises(ValidationError):
        ListProcessesArgs.model_validate({})


def test_strict_schema_normalizes_nested_defs_recursively() -> None:
    schema = strict_schema(_NestedArgs)

    _walk_objects(schema)
    assert schema["$defs"]["_NestedLeaf"]["additionalProperties"] is False


class _RejectedKeywordModel(BaseModel):
    model_config = ConfigDict(json_schema_extra={"allOf": []})
    value: str


def test_strict_schema_rejects_unsupported_keywords() -> None:
    with pytest.raises(ValueError, match="allOf"):
        strict_schema(_RejectedKeywordModel)
