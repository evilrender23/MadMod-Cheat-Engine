"""Safety policy and workflow states for agent tool invocations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from mempilot.core.backend import ProcessIdentity

if TYPE_CHECKING:
    from mempilot.agent.tools import ToolDef


class FlowState(StrEnum):
    NO_PROCESS = "no_process"
    ATTACHED = "attached"
    SCANNING = "scanning"
    CANDIDATES = "candidates"
    AWAITING_CHANGE = "awaiting_change"
    NARROWED = "narrowed"
    WATCHING = "watching"


class AgentMode(StrEnum):
    OFF = "off"
    GUIDED = "guided"
    AUTONOMOUS = "autonomous"


class Decision(StrEnum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


@dataclass(slots=True)
class AgentPolicy:
    """Evaluate one tool against process binding, mode, workflow, and write quota."""

    mode: AgentMode = AgentMode.GUIDED
    write_limit: int = 20
    writes_used: int = 0
    bound_identity: ProcessIdentity | None = None

    def evaluate(
        self,
        tool: ToolDef,
        state: FlowState,
        current: ProcessIdentity | None,
    ) -> tuple[Decision, str]:
        """Return the policy decision and an actionable Spanish explanation."""
        if self.mode is AgentMode.OFF:
            return Decision.DENY, "La IA está desactivada. Actívala en Ajustes → IA."

        if self.mode is AgentMode.AUTONOMOUS and tool.name in {
            "attach_process",
            "detach_process",
        }:
            return Decision.DENY, "El modo autónomo no puede cambiar de proceso."

        if tool.requires_attached and current is None:
            return Decision.DENY, "Pide al usuario que seleccione un proceso."

        if self.mode is AgentMode.AUTONOMOUS and not self._matches_bound_process(current):
            self.mode = AgentMode.GUIDED
            self.bound_identity = None
            return (
                Decision.DENY,
                "El proceso ya no coincide con la autorización. "
                "Se desactivó el modo autónomo; pide al usuario que lo autorice de nuevo.",
            )

        if tool.mutating and self.mode is AgentMode.GUIDED:
            return Decision.CONFIRM, "Esta acción requiere confirmación del usuario."

        if tool.mutating and self.mode is AgentMode.AUTONOMOUS:
            if self.writes_used >= self.write_limit:
                return (
                    Decision.DENY,
                    f"Límite de {self.write_limit} escrituras alcanzado; "
                    "el usuario debe ampliarlo en Ajustes.",
                )
            self.writes_used += 1
            return Decision.ALLOW, "Acción autorizada dentro del límite de escrituras."

        if tool.allowed_states is not None and state not in tool.allowed_states:
            expected = ", ".join(sorted(item.value for item in tool.allowed_states))
            return (
                Decision.DENY,
                f"La herramienta no está disponible en el paso {state.value}. "
                f"Completa antes el paso adecuado: {expected}.",
            )

        return Decision.ALLOW, "Acción de solo lectura autorizada."

    def _matches_bound_process(self, current: ProcessIdentity | None) -> bool:
        return (
            current is not None
            and self.bound_identity is not None
            and current.matches(self.bound_identity)
        )
