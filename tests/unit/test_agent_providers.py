"""Focused contracts for Step 3.2 provider payloads and local replay."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

import mempilot.agent.providers as providers_module
from mempilot.agent.conversation import Conversation
from mempilot.agent.providers import (
    OpenAIResponsesProvider,
    ProviderTurn,
    ScriptedProvider,
    ToolCall,
)
from mempilot.config.settings import AISettings
from mempilot.core.exceptions import ProviderError


class _Responses:
    def __init__(self, output: list[object], text: str = "") -> None:
        self.output = output
        self.text = text
        self.payload: dict[str, object] | None = None

    def create(self, **payload: object) -> object:
        self.payload = payload
        return SimpleNamespace(output=self.output, output_text=self.text)


class _RaisingResponses:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def create(self, **payload: object) -> object:
        del payload
        raise self._error


def test_openai_responses_provider_uses_exact_non_stored_flat_payload() -> None:
    function_call = SimpleNamespace(
        type="function_call",
        call_id="call-1",
        name="read_address",
        arguments='{"address":4096,"data_type":"int32"}',
    )
    responses = _Responses([function_call], "Leyendo.")
    client = SimpleNamespace(responses=responses)
    settings = AISettings(model="gpt-4.1", timeout_s=7.0, max_retries=0)
    provider = OpenAIResponsesProvider(
        "sk-test-not-real-123456",
        settings,
        client=cast(Any, client),
    )
    tools = [
        {
            "type": "function",
            "name": "read_address",
            "description": "Lee una dirección.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            "strict": True,
        }
    ]
    input_items: list[Any] = [{"role": "user", "content": "Lee 0x1000"}]

    turn = provider.complete("instrucciones", input_items, tools)

    assert responses.payload == {
        "model": "gpt-4.1",
        "instructions": "instrucciones",
        "input": input_items,
        "tools": tools,
        "parallel_tool_calls": False,
        "store": False,
        "max_output_tokens": 4096,
    }
    assert turn.text == "Leyendo."
    assert turn.tool_calls == [
        ToolCall("call-1", "read_address", '{"address":4096,"data_type":"int32"}')
    ]
    assert turn.raw_output == [function_call]


def test_openai_client_receives_only_configured_connection_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _Client:
        def __init__(self, **options: object) -> None:
            captured.update(options)

    monkeypatch.setattr(providers_module, "OpenAI", _Client)

    OpenAIResponsesProvider(
        "sk-test-not-real-123456",
        AISettings(base_url="https://provider.invalid/v1", timeout_s=9.5, max_retries=4),
    )

    assert captured == {
        "api_key": "sk-test-not-real-123456",
        "base_url": "https://provider.invalid/v1",
        "timeout": 9.5,
        "max_retries": 4,
    }


@pytest.mark.parametrize(
    ("raised_name", "expected"),
    [
        ("APITimeoutError", "no respondió a tiempo"),
        ("RateLimitError", "Límite de peticiones"),
        ("AuthenticationError", "Clave de API inválida"),
        ("BadRequestError", "Petición rechazada"),
        ("APIConnectionError", "Sin conexión"),
        ("APIStatusError", "HTTP 503 · solicitud req-provider-unique"),
    ],
)
def test_provider_errors_are_mapped_without_exposing_raw_details(
    monkeypatch: pytest.MonkeyPatch,
    raised_name: str,
    expected: str,
) -> None:
    exception_types = {
        name: type(f"_Fake{name}", (Exception,), {})
        for name in (
            "APITimeoutError",
            "RateLimitError",
            "AuthenticationError",
            "BadRequestError",
            "APIConnectionError",
            "APIStatusError",
        )
    }
    for name, exception_type in exception_types.items():
        monkeypatch.setattr(providers_module, name, exception_type)
    error = exception_types[raised_name]("raw provider secret")
    if raised_name == "APIStatusError":
        error.status_code = 503
        error.request_id = "req-provider-unique"
    client = SimpleNamespace(responses=_RaisingResponses(error))
    provider = OpenAIResponsesProvider(
        "sk-test-not-real-123456",
        AISettings(),
        client=cast(Any, client),
    )

    with pytest.raises(ProviderError, match=expected) as captured:
        provider.complete("prompt", [], [])

    assert "raw provider secret" not in str(captured.value)


def test_scripted_provider_replay_prepends_only_fresh_state() -> None:
    scripted = ScriptedProvider(
        [
            ProviderTurn(
                "",
                [ToolCall("scan-1", "get_scan_status", "{}")],
                [],
            ),
            ProviderTurn("Escaneo listo.", [], []),
        ]
    )
    conversation = Conversation()
    conversation.add_user("Busca la vida")
    first = scripted.complete("prompt", conversation.provider_input("[ESTADO] uno"), [])
    conversation.add_provider_turn(first)
    conversation.add_tool_output(first.tool_calls[0], '{"ok":true}')
    scripted.complete("prompt", conversation.provider_input("[ESTADO] dos"), [])

    second_input = scripted.requests[1][1]
    assert second_input[0] == {"role": "system", "content": "[ESTADO] dos"}
    assert {"role": "system", "content": "[ESTADO] uno"} not in second_input
    assert {
        "type": "function_call_output",
        "call_id": "scan-1",
        "output": '{"ok":true}',
    } in second_input


def test_scripted_provider_exhaustion_is_actionable() -> None:
    provider = ScriptedProvider([])
    with pytest.raises(ProviderError, match="agotó los turnos"):
        provider.complete("prompt", [], [])
