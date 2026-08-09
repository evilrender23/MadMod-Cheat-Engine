"""Safe adapters for authenticated local AI command-line clients."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mempilot.config.settings import AISettings, CLIBackend
from mempilot.core.exceptions import ProviderError

_MAX_TOOL_CALLS = 32
_MAX_ANTIGRAVITY_PROMPT_CHARS = 24_000
_PROVIDER_NAMES = {
    CLIBackend.ANTIGRAVITY: "Antigravity CLI",
    CLIBackend.CODEX: "Codex CLI",
    CLIBackend.CLAUDE: "Claude Code",
}


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One sequential function call requested by the model."""

    call_id: str
    name: str
    arguments_json: str


@dataclass(frozen=True, slots=True)
class ProviderTurn:
    """Normalized provider response, including replayable raw output items."""

    text: str
    tool_calls: list[ToolCall]
    raw_output: list[Any]


class AIProvider(Protocol):
    """Synchronous provider contract consumed only from an AgentWorker thread."""

    name: str

    def complete(
        self,
        instructions: str,
        input_items: list[Any],
        tools: list[dict[str, Any]],
    ) -> ProviderTurn:
        """Complete one non-streaming model turn."""
        ...


class _RequestedTool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    arguments_json: str


class _CLIEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    tool_calls: list[_RequestedTool] = Field(max_length=_MAX_TOOL_CALLS)


class CLIProvider:
    """Run one isolated, structured-output turn through an authenticated AI CLI."""

    def __init__(self, executable: str, settings: AISettings) -> None:
        if not executable:
            raise ValueError("La ruta del ejecutable CLI no puede estar vacía.")
        self._executable = executable
        self._settings = settings.model_copy(deep=True)
        self.name = _PROVIDER_NAMES[settings.provider]

    def complete(
        self,
        instructions: str,
        input_items: list[Any],
        tools: list[dict[str, Any]],
    ) -> ProviderTurn:
        """Request exactly one JSON decision without granting the CLI access to app tools."""
        if self._settings.provider is CLIBackend.ANTIGRAVITY:
            prompt = _bounded_antigravity_prompt(instructions, input_items, tools)
        else:
            prompt = _render_prompt(instructions, input_items, tools)
        schema = _response_schema(tools)
        raw = self._run(prompt, schema)
        envelope = _parse_envelope(self._settings.provider, raw)
        calls: list[ToolCall] = []
        for requested in envelope.tool_calls:
            try:
                arguments = json.loads(requested.arguments_json)
            except json.JSONDecodeError:
                raise ProviderError(
                    f"{self.name} devolvió argumentos JSON inválidos para "
                    f"{requested.name!r}. Inténtalo de nuevo."
                ) from None
            if not isinstance(arguments, dict):
                raise ProviderError(
                    f"{self.name} devolvió argumentos no estructurados para "
                    f"{requested.name!r}. Inténtalo de nuevo."
                )
            calls.append(
                ToolCall(
                    call_id=f"cli-{uuid.uuid4().hex}",
                    name=requested.name,
                    arguments_json=json.dumps(arguments, ensure_ascii=False, separators=(",", ":")),
                )
            )
        return ProviderTurn(envelope.text, calls, [])

    def _run(self, prompt: str, schema: dict[str, Any]) -> str:
        schema_json = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
        environment = _clean_environment()
        creation_flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            with tempfile.TemporaryDirectory(prefix="mempilot-cli-") as temporary:
                working_dir = Path(temporary)
                command, standard_input = self._command(
                    prompt,
                    schema,
                    schema_json,
                    working_dir,
                )
                completed = subprocess.run(
                    command,
                    cwd=working_dir,
                    input=standard_input,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self._settings.timeout_s,
                    check=False,
                    env=environment,
                    creationflags=creation_flags,
                )
        except subprocess.TimeoutExpired:
            raise ProviderError(
                f"{self.name} no respondió en {self._settings.timeout_s:g} s. "
                "Aumenta el tiempo de espera en Ajustes → IA."
            ) from None
        except OSError:
            raise ProviderError(
                f"No se pudo iniciar {self.name}. Comprueba la ruta en Ajustes → IA."
            ) from None
        if completed.returncode != 0:
            hint = _failure_hint(self._settings.provider, completed.stderr)
            raise ProviderError(f"{self.name} terminó con el código {completed.returncode}. {hint}")
        if not completed.stdout.strip():
            raise ProviderError(
                f"{self.name} no produjo una respuesta. Comprueba que la sesión esté iniciada "
                "y que el modelo seleccionado admita salida estructurada."
            )
        return completed.stdout

    def _command(
        self,
        prompt: str,
        schema: dict[str, Any],
        schema_json: str,
        working_dir: Path,
    ) -> tuple[list[str], str | None]:
        provider = self._settings.provider
        model = self._settings.model
        if provider is CLIBackend.ANTIGRAVITY:
            command = [
                self._executable,
                "--print",
                prompt,
                "--output-format",
                "json",
                "--json-schema",
                schema_json,
                "--mode",
                "plan",
                "--sandbox",
                "--disable-slash-commands",
                "--print-timeout",
                f"{max(1, math.ceil(self._settings.timeout_s))}s",
            ]
            if model:
                command.extend(("--model", model))
            return command, None
        if provider is CLIBackend.CODEX:
            schema_path = working_dir / "response-schema.json"
            schema_path.write_text(
                json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            command = [self._executable]
            if model:
                command.extend(("--model", model))
            command.extend(
                (
                    "--ask-for-approval",
                    "never",
                    "--disable",
                    "shell_tool",
                    "--disable",
                    "apps",
                    "--disable",
                    "browser_use",
                    "--disable",
                    "computer_use",
                    "--disable",
                    "multi_agent",
                    "exec",
                    "--sandbox",
                    "read-only",
                    "--skip-git-repo-check",
                    "--ephemeral",
                    "--ignore-user-config",
                    "--ignore-rules",
                    "--output-schema",
                    str(schema_path),
                    "--color",
                    "never",
                    "-",
                )
            )
            return command, prompt
        command = [
            self._executable,
            "--print",
            "--output-format",
            "json",
            "--json-schema",
            schema_json,
            "--tools",
            "",
            "--no-session-persistence",
            "--safe-mode",
            "--permission-mode",
            "plan",
        ]
        if model:
            command.extend(("--model", model))
        return command, prompt


def find_cli_executable(settings: AISettings) -> str | None:
    """Resolve an explicit executable or the selected CLI command through PATH."""
    configured = (settings.executable or "").strip()
    candidate = configured or settings.provider.value
    expanded = Path(candidate).expanduser()
    if expanded.is_file():
        return str(expanded.resolve())
    return shutil.which(candidate)


def create_cli_provider(settings: AISettings) -> CLIProvider | None:
    """Build the selected provider when enabled and installed."""
    if not settings.enabled:
        return None
    executable = find_cli_executable(settings)
    return CLIProvider(executable, settings) if executable is not None else None


def _render_prompt(
    instructions: str,
    input_items: list[Any],
    tools: list[dict[str, Any]],
) -> str:
    payload = {
        "conversation": input_items,
        "available_tools": tools,
    }
    return (
        f"{instructions.strip()}\n\n"
        "REGLAS DEL ADAPTADOR CLI:\n"
        "Eres únicamente el motor de decisión integrado en M@D-Engine. No uses herramientas "
        "internas de la CLI, no ejecutes comandos y no leas ni modifiques archivos. Las únicas "
        "acciones permitidas son las herramientas tipadas de available_tools. Para solicitar "
        "acciones, devuelve tool_calls; M@D-Engine las validará, aplicará su política y devolverá "
        "los resultados en el turno siguiente. Usa arguments_json con un objeto JSON codificado "
        "como texto. Devuelve texto final sólo cuando no necesites otra herramienta.\n\n"
        f"ENTRADA_MAD_MOD_ENGINE={json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
    )


def _bounded_antigravity_prompt(
    instructions: str,
    input_items: list[Any],
    tools: list[dict[str, Any]],
) -> str:
    """Keep Antigravity below the Windows command-line limit by pruning old replay."""
    prompt = _render_prompt(instructions, input_items, tools)
    if len(prompt) <= _MAX_ANTIGRAVITY_PROMPT_CHARS:
        return prompt

    state = input_items[:1] if _is_role(input_items[:1], "system") else []
    history = _semantic_replay(input_items[len(state) :])
    turns = _conversation_turns(history)
    notice = {
        "role": "system",
        "content": (
            "M@D-Engine compactó contexto antiguo para respetar el límite de Antigravity. "
            "El estado de proceso más reciente es autoritativo."
        ),
    }

    while turns:
        compacted = [*state, notice, *(item for turn in turns for item in turn)]
        prompt = _render_prompt(instructions, compacted, tools)
        if len(prompt) <= _MAX_ANTIGRAVITY_PROMPT_CHARS:
            return prompt
        if len(turns) > 1:
            turns.pop(0)
            continue
        turn = turns[0]
        protected = {index for index, item in enumerate(turn) if _is_role([item], "user")}
        if turn:
            protected.add(len(turn) - 1)
        removable = next(
            (index for index in range(len(turn)) if index not in protected),
            None,
        )
        if removable is None:
            break
        turn.pop(removable)

    raise ProviderError(
        "La petición actual es demasiado grande para Antigravity CLI. "
        "Usa un mensaje más breve o solicita menos resultados."
    )


def _semantic_replay(items: list[Any]) -> list[Any]:
    """Collapse function call/output pairs into compact, self-describing replay events."""
    events: list[Any] = []
    pending: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            events.append(item)
            continue
        kind = item.get("type")
        call_id = item.get("call_id")
        if kind == "function_call" and isinstance(call_id, str):
            pending[call_id] = item
            continue
        if kind == "function_call_output" and isinstance(call_id, str):
            call = pending.pop(call_id, None)
            result = item.get("output", "")
            if isinstance(result, str):
                with suppress(json.JSONDecodeError):
                    result = json.loads(result)
            events.append(
                {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "herramienta": call.get("name", "desconocida")
                            if call is not None
                            else "desconocida",
                            "argumentos": call.get("arguments", "{}") if call is not None else "{}",
                            "resultado": result,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }
            )
            continue
        events.append(item)
    events.extend(pending.values())
    return events


def _conversation_turns(items: list[Any]) -> list[list[Any]]:
    turns: list[list[Any]] = []
    for item in items:
        if _is_role([item], "user") or not turns:
            turns.append([item])
        else:
            turns[-1].append(item)
    return turns


def _is_role(items: list[Any], role: str) -> bool:
    return bool(items and isinstance(items[0], dict) and items[0].get("role") == role)


def _response_schema(tools: list[dict[str, Any]]) -> dict[str, Any]:
    names = [name for tool in tools if isinstance(name := tool.get("name"), str)]
    name_schema: dict[str, Any] = {"type": "string"}
    if names:
        name_schema["enum"] = names
    return {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "tool_calls": {
                "type": "array",
                "maxItems": _MAX_TOOL_CALLS,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": name_schema,
                        "arguments_json": {"type": "string"},
                    },
                    "required": ["name", "arguments_json"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["text", "tool_calls"],
        "additionalProperties": False,
    }


def _parse_envelope(provider: CLIBackend, raw: str) -> _CLIEnvelope:
    try:
        document = json.loads(raw)
        if provider is CLIBackend.ANTIGRAVITY:
            if document.get("status") != "SUCCESS":
                raise ValueError
            document = document["structured_output"]
        elif provider is CLIBackend.CLAUDE:
            if document.get("is_error") is not False:
                raise ValueError
            document = document["structured_output"]
        return _CLIEnvelope.model_validate(document)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, ValidationError):
        raise ProviderError(
            f"{_PROVIDER_NAMES[provider]} devolvió una respuesta incompatible. "
            "Comprueba el modelo seleccionado e inténtalo de nuevo."
        ) from None


def _clean_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"):
        environment.pop(name, None)
    environment["NO_COLOR"] = "1"
    environment["TERM"] = "dumb"
    return environment


def _failure_hint(provider: CLIBackend, stderr: str) -> str:
    lowered = stderr.casefold()
    if any(marker in lowered for marker in ("login", "auth", "credential", "unauthorized")):
        return f"Inicia sesión directamente con «{provider.value}» y vuelve a intentarlo."
    return "Comprueba la instalación, la sesión iniciada y el modelo en Ajustes → IA."


class ScriptedProvider:
    """Deterministic provider for tests; it never starts an external process."""

    name = "ScriptedProvider"

    def __init__(self, turns: list[ProviderTurn]) -> None:
        self._turns = list(turns)
        self._index = 0
        self.requests: list[tuple[str, list[Any], list[dict[str, Any]]]] = []

    def complete(
        self,
        instructions: str,
        input_items: list[Any],
        tools: list[dict[str, Any]],
    ) -> ProviderTurn:
        """Return the next programmed turn and retain a shallow request snapshot."""
        self.requests.append((instructions, list(input_items), list(tools)))
        if self._index >= len(self._turns):
            raise ProviderError(
                "El proveedor de prueba agotó los turnos programados. "
                "Añade otro ProviderTurn al guion."
            )
        turn = self._turns[self._index]
        self._index += 1
        return turn
