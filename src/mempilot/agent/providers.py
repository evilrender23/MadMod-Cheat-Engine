"""AI provider adapters for local-replay Responses API conversations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, cast

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    RateLimitError,
)
from openai.types.responses.response_function_tool_call import ResponseFunctionToolCall
from openai.types.responses.response_input_param import ResponseInputParam

from mempilot.config.settings import AISettings
from mempilot.core.exceptions import ProviderError


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


class OpenAIResponsesProvider:
    """OpenAI Responses API adapter with local replay and server storage disabled."""

    name = "OpenAI"

    def __init__(
        self,
        api_key: str,
        settings: AISettings,
        *,
        client: OpenAI | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("La clave de API no puede estar vacía.")
        self._settings = settings
        self._client = client or OpenAI(
            api_key=api_key,
            base_url=settings.base_url or None,
            timeout=settings.timeout_s,
            max_retries=settings.max_retries,
        )

    def complete(
        self,
        instructions: str,
        input_items: list[Any],
        tools: list[dict[str, Any]],
    ) -> ProviderTurn:
        """Send the exact flat-tool Responses payload and normalize its output."""
        try:
            response = self._client.responses.create(
                model=self._settings.model,
                instructions=instructions,
                input=cast("ResponseInputParam", input_items),
                tools=tools,  # type: ignore[arg-type]
                parallel_tool_calls=False,
                store=False,
                max_output_tokens=4096,
            )
        except APITimeoutError as exc:
            raise ProviderError(
                "El proveedor no respondió a tiempo. Revisa la conexión e inténtalo de nuevo."
            ) from exc
        except RateLimitError as exc:
            raise ProviderError(
                "Límite de peticiones alcanzado. Espera un momento e inténtalo de nuevo."
            ) from exc
        except AuthenticationError as exc:
            raise ProviderError(
                "Clave de API inválida. Revísala en Ajustes → IA e inténtalo de nuevo."
            ) from exc
        except BadRequestError as exc:
            raise ProviderError(
                "Petición rechazada por el proveedor. Revisa el modelo configurado en Ajustes → IA."
            ) from exc
        except APIConnectionError as exc:
            raise ProviderError(
                "Sin conexión con el proveedor. Comprueba la red y la URL base configurada."
            ) from exc
        except APIStatusError as exc:
            status = getattr(exc, "status_code", "desconocido")
            request_id = getattr(exc, "request_id", None)
            suffix = f" · solicitud {request_id}" if request_id else ""
            raise ProviderError(
                f"El proveedor devolvió el estado HTTP {status}{suffix}. "
                "Revisa la configuración e inténtalo de nuevo."
            ) from exc

        calls: list[ToolCall] = []
        for item in response.output:
            if getattr(item, "type", None) != "function_call":
                continue
            function_call = cast("ResponseFunctionToolCall", item)
            calls.append(
                ToolCall(
                    call_id=str(function_call.call_id),
                    name=str(function_call.name),
                    arguments_json=str(function_call.arguments),
                )
            )
        return ProviderTurn(
            text=response.output_text or "",
            tool_calls=calls,
            raw_output=list(response.output),
        )


class ScriptedProvider:
    """Deterministic provider for tests; it never performs network access."""

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
