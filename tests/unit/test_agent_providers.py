"""Focused contracts for isolated CLI providers and local conversation replay."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import mempilot.agent.providers as providers_module
from mempilot.agent.conversation import Conversation
from mempilot.agent.providers import (
    CLIProvider,
    ProviderTurn,
    ScriptedProvider,
    ToolCall,
    create_cli_provider,
    find_cli_executable,
)
from mempilot.config.settings import AISettings, CLIBackend
from mempilot.core.exceptions import ProviderError
from mempilot.i18n import Language, get_language, set_language

_TOOL_SPEC = {
    "type": "function",
    "name": "read_address",
    "description": "Lee una dirección.",
    "parameters": {
        "type": "object",
        "properties": {"address": {"type": "integer"}},
        "required": ["address"],
        "additionalProperties": False,
    },
    "strict": True,
}
_ENVELOPE = {
    "text": "Leyendo.",
    "tool_calls": [{"name": "read_address", "arguments_json": '{"address":4096}'}],
}


def _provider_output(backend: CLIBackend) -> str:
    if backend is CLIBackend.ANTIGRAVITY:
        return json.dumps({"status": "SUCCESS", "structured_output": _ENVELOPE})
    if backend is CLIBackend.CLAUDE:
        return json.dumps({"is_error": False, "structured_output": _ENVELOPE})
    return json.dumps(_ENVELOPE)


@pytest.mark.parametrize("backend", list(CLIBackend))
def test_cli_provider_runs_isolated_structured_turn_without_api_keys(
    monkeypatch: pytest.MonkeyPatch,
    backend: CLIBackend,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
        captured.update(command=command, **options)
        if backend is CLIBackend.CODEX:
            schema_path = Path(command[command.index("--output-schema") + 1])
            assert schema_path.is_file()
            assert (
                json.loads(schema_path.read_text(encoding="utf-8"))["additionalProperties"] is False
            )
        return subprocess.CompletedProcess(command, 0, _provider_output(backend), "")

    monkeypatch.setattr(providers_module.subprocess, "run", fake_run)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-child")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-reach-child")
    provider = CLIProvider(
        f"C:/tools/{backend.value}.exe",
        AISettings(provider=backend, timeout_s=17.0),
    )

    turn = provider.complete(
        "Instrucciones seguras",
        [{"role": "user", "content": "Lee 0x1000"}],
        [_TOOL_SPEC],
    )

    command = captured["command"]
    assert command[0] == f"C:/tools/{backend.value}.exe"
    assert captured["cwd"] != Path.cwd()
    assert captured["timeout"] == 17.0
    assert captured["env"]["NO_COLOR"] == "1"
    assert "OPENAI_API_KEY" not in captured["env"]
    assert "ANTHROPIC_API_KEY" not in captured["env"]
    if backend is CLIBackend.ANTIGRAVITY:
        assert captured["input"] is None
        prompt = command[command.index("--print") + 1]
        assert "Lee 0x1000" in prompt
        assert "--sandbox" in command
        assert "--dangerously-skip-permissions" not in command
    elif backend is CLIBackend.CODEX:
        assert "--disable" in command
        assert "shell_tool" in command
        assert "--ignore-user-config" in command
        assert "read-only" in command
        assert "Lee 0x1000" in captured["input"]
    else:
        assert command[command.index("--tools") + 1] == ""
        assert "--safe-mode" in command
        assert "--no-session-persistence" in command
        assert "Lee 0x1000" in captured["input"]
    assert turn.text == "Leyendo."
    assert len(turn.tool_calls) == 1
    assert turn.tool_calls[0].call_id.startswith("cli-")
    assert turn.tool_calls[0].name == "read_address"
    assert turn.tool_calls[0].arguments_json == '{"address":4096}'
    assert turn.raw_output == []


def test_cli_adapter_uses_english_rules_when_english_is_active() -> None:
    previous = get_language()
    try:
        set_language(Language.ENGLISH)
        prompt = providers_module._render_prompt(
            "Safe instructions",
            [{"role": "user", "content": "Read the value"}],
            [_TOOL_SPEC],
        )
    finally:
        set_language(previous)

    assert "CLI ADAPTER RULES" in prompt
    assert "MAD_MOD_ENGINE_INPUT=" in prompt
    assert "REGLAS DEL ADAPTADOR CLI" not in prompt


def test_antigravity_compacts_old_turns_instead_of_rejecting_long_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_prompt = ""

    def fake_run(command: list[str], **_options: Any) -> subprocess.CompletedProcess[str]:
        nonlocal captured_prompt
        captured_prompt = command[command.index("--print") + 1]
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps(
                {
                    "status": "SUCCESS",
                    "structured_output": {"text": "Continuamos.", "tool_calls": []},
                }
            ),
            "",
        )

    monkeypatch.setattr(providers_module, "_MAX_ANTIGRAVITY_PROMPT_CHARS", 2500)
    monkeypatch.setattr(providers_module.subprocess, "run", fake_run)
    replay: list[Any] = [{"role": "system", "content": "estado actual"}]
    for index in range(8):
        replay.extend(
            (
                {"role": "user", "content": f"turno-{index} " + "u" * 350},
                {"role": "assistant", "content": f"respuesta-{index} " + "a" * 350},
            )
        )

    turn = CLIProvider(
        "agy.exe",
        AISettings(provider=CLIBackend.ANTIGRAVITY),
    ).complete("Instrucciones seguras", replay, [_TOOL_SPEC])

    assert turn.text == "Continuamos."
    assert len(captured_prompt) <= 2500
    assert "estado actual" in captured_prompt
    assert "turno-7" in captured_prompt
    assert "turno-0" not in captured_prompt
    assert "compactó contexto antiguo" in captured_prompt


def test_cli_provider_passes_optional_model_to_selected_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    def fake_run(command: list[str], **_options: Any) -> subprocess.CompletedProcess[str]:
        captured.extend(command)
        return subprocess.CompletedProcess(
            command, 0, json.dumps({"text": "ok", "tool_calls": []}), ""
        )

    monkeypatch.setattr(providers_module.subprocess, "run", fake_run)
    CLIProvider(
        "codex.exe",
        AISettings(provider=CLIBackend.CODEX, model="gpt-test"),
    ).complete("prompt", [], [])

    assert captured[captured.index("--model") + 1] == "gpt-test"


def test_cli_provider_maps_timeout_without_exposing_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout(command: list[str], **_options: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, 9.0, output="private output")

    monkeypatch.setattr(providers_module.subprocess, "run", timeout)
    provider = CLIProvider("codex.exe", AISettings(provider=CLIBackend.CODEX, timeout_s=9.0))

    with pytest.raises(ProviderError, match="no respondió en 9 s") as captured:
        provider.complete("prompt private", [], [])

    assert "private" not in str(captured.value)


def test_cli_provider_maps_auth_failure_without_raw_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failed(command: list[str], **_options: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 7, "", "Authentication token secret-value")

    monkeypatch.setattr(providers_module.subprocess, "run", failed)
    provider = CLIProvider("claude.exe", AISettings(provider=CLIBackend.CLAUDE))

    with pytest.raises(ProviderError, match=r"Inicia sesión.*claude") as captured:
        provider.complete("prompt", [], [])

    assert "secret-value" not in str(captured.value)


@pytest.mark.parametrize(
    "output",
    [
        "not-json",
        json.dumps({"text": "missing calls"}),
        json.dumps({"text": "", "tool_calls": [{"name": "x", "arguments_json": "[]"}]}),
    ],
)
def test_cli_provider_rejects_incompatible_output(
    monkeypatch: pytest.MonkeyPatch,
    output: str,
) -> None:
    def fake_run(command: list[str], **_options: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(providers_module.subprocess, "run", fake_run)
    provider = CLIProvider("codex.exe", AISettings(provider=CLIBackend.CODEX))

    with pytest.raises(ProviderError, match=r"(incompatible|no estructurados)"):
        provider.complete("prompt", [], [])


def test_cli_executable_resolution_uses_override_then_selected_command(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "custom-cli.exe"
    executable.write_bytes(b"")
    explicit = AISettings(provider=CLIBackend.CLAUDE, executable=str(executable))
    assert find_cli_executable(explicit) == str(executable.resolve())

    monkeypatch.setattr(
        providers_module.shutil,
        "which",
        lambda command: f"C:/bin/{command}.exe",
    )
    automatic = AISettings(provider=CLIBackend.ANTIGRAVITY)
    assert find_cli_executable(automatic) == "C:/bin/agy.exe"
    assert create_cli_provider(automatic) is not None
    assert create_cli_provider(automatic).name == "Antigravity CLI"  # type: ignore[union-attr]
    assert create_cli_provider(automatic.model_copy(update={"enabled": False})) is None


def test_scripted_provider_replay_prepends_only_fresh_state() -> None:
    scripted = ScriptedProvider(
        [
            ProviderTurn("", [ToolCall("scan-1", "get_scan_status", "{}")], []),
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
