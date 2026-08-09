"""Safety policy and workflow states for agent tool invocations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from mempilot.core.backend import ProcessIdentity
from mempilot.i18n import t

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
        """Return the policy decision and an actionable localized explanation."""
        if self.mode is AgentMode.OFF:
            return Decision.DENY, t("policy.ai_off")

        if self.mode is AgentMode.AUTONOMOUS and tool.name in {
            "attach_process",
            "detach_process",
        }:
            return Decision.DENY, t("policy.autonomous_process")

        if tool.requires_attached and current is None:
            return Decision.DENY, t("policy.select_process")

        if self.mode is AgentMode.AUTONOMOUS and not self._matches_bound_process(current):
            self.mode = AgentMode.GUIDED
            self.bound_identity = None
            return Decision.DENY, t("policy.identity_changed")

        if tool.always_confirm:
            return Decision.CONFIRM, t("policy.confirm_trainer")
        if tool.mutating and self.mode is AgentMode.GUIDED:
            return Decision.CONFIRM, t("policy.confirm_action")

        if tool.mutating and self.mode is AgentMode.AUTONOMOUS:
            if self.writes_used >= self.write_limit:
                return Decision.DENY, t("policy.write_limit", limit=self.write_limit)
            self.writes_used += 1
            return Decision.ALLOW, t("policy.autonomous_allowed")

        if tool.allowed_states is not None and state not in tool.allowed_states:
            expected = ", ".join(sorted(item.value for item in tool.allowed_states))
            return Decision.DENY, t(
                "policy.state_denied",
                state=state.value,
                expected=expected,
            )

        return Decision.ALLOW, t("policy.read_allowed")

    def _matches_bound_process(self, current: ProcessIdentity | None) -> bool:
        return (
            current is not None
            and self.bound_identity is not None
            and current.matches(self.bound_identity)
        )
