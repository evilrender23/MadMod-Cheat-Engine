"""Contracts for strict Responses API schemas."""

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from mempilot.agent.policies import AgentPolicy
from mempilot.agent.schemas import ListProcessesArgs, strict_schema
from mempilot.agent.tools import ToolRegistry


class _ControllerStub:
    pass


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
        if isinstance(node.get("properties"), dict):
            assert node["additionalProperties"] is False
            assert node["required"] == list(node["properties"])
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


def test_arguments_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ListProcessesArgs.model_validate({"query": None, "unexpected": True})


def test_optional_fields_are_still_required_by_strict_contract() -> None:
    with pytest.raises(ValidationError):
        ListProcessesArgs.model_validate({})


class _RejectedKeywordModel(BaseModel):
    model_config = ConfigDict(json_schema_extra={"allOf": []})
    value: str


def test_strict_schema_rejects_unsupported_keywords() -> None:
    with pytest.raises(ValueError, match="allOf"):
        strict_schema(_RejectedKeywordModel)
