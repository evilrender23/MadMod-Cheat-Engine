"""Local conversation replay for providers configured with ``store=False``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mempilot.agent.providers import ProviderTurn, ToolCall
from mempilot.i18n import t


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    """One user-visible transcript message retained only in local memory."""

    role: str
    text: str


@dataclass(slots=True)
class Conversation:
    """Own replayable provider items and the separate user-visible transcript."""

    input_items: list[Any] = field(default_factory=list)
    messages: list[ConversationMessage] = field(default_factory=list)

    def add_user(self, text: str) -> None:
        """Append a user message to both replay and visible transcript."""
        normalized = text.strip()
        if not normalized:
            raise ValueError(t("chat.message_required"))
        self.input_items.append({"role": "user", "content": normalized})
        self.messages.append(ConversationMessage("user", normalized))

    def provider_input(self, current_state: str) -> list[Any]:
        """Return full local replay with exactly one fresh state item at the front."""
        return [{"role": "system", "content": current_state}, *self.input_items]

    def add_provider_turn(self, turn: ProviderTurn) -> None:
        """Retain raw Responses output, synthesizing equivalent items for scripted turns."""
        if turn.raw_output:
            self.input_items.extend(turn.raw_output)
        else:
            if turn.text:
                self.input_items.append({"role": "assistant", "content": turn.text})
            self.input_items.extend(_tool_call_item(call) for call in turn.tool_calls)
        normalized = turn.text.strip()
        if normalized:
            self.messages.append(ConversationMessage("assistant", normalized))

    def add_tool_output(self, call: ToolCall, result_json: str) -> None:
        """Append the Responses function output item needed by the next local replay."""
        self.input_items.append(
            {
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": result_json,
            }
        )

    def clear(self) -> None:
        """Discard all locally retained process context and visible messages."""
        self.input_items.clear()
        self.messages.clear()


def _tool_call_item(call: ToolCall) -> dict[str, str]:
    return {
        "type": "function_call",
        "call_id": call.call_id,
        "name": call.name,
        "arguments": call.arguments_json,
    }
