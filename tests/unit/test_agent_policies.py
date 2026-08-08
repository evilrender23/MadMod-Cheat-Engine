"""The seven ordered AgentPolicy safety rules."""

from pydantic import BaseModel

from mempilot.agent.policies import AgentMode, AgentPolicy, Decision, FlowState
from mempilot.agent.schemas import OperationResult
from mempilot.agent.tools import ToolDef
from mempilot.core.backend import Architecture, ProcessIdentity


class _Args(BaseModel):
    pass


def _handler(args: BaseModel) -> BaseModel:
    return OperationResult(ok=True, message=str(args))


def _tool(
    name: str = "read_address",
    *,
    mutating: bool = False,
    attached: bool = False,
    states: frozenset[FlowState] | None = None,
) -> ToolDef:
    return ToolDef(name, "prueba", _Args, _handler, mutating, attached, states)


def _identity(pid: int = 101, created: float = 1.0) -> ProcessIdentity:
    return ProcessIdentity(pid, "lab.exe", created, None, Architecture.X64)


def test_off_mode_denies_every_tool() -> None:
    policy = AgentPolicy(mode=AgentMode.OFF)

    decision, reason = policy.evaluate(_tool(), FlowState.NO_PROCESS, None)

    assert decision is Decision.DENY
    assert "desactivada" in reason


def test_autonomous_mode_cannot_attach_or_detach() -> None:
    identity = _identity()
    policy = AgentPolicy(mode=AgentMode.AUTONOMOUS, bound_identity=identity)

    for name in ("attach_process", "detach_process"):
        decision, reason = policy.evaluate(_tool(name), FlowState.ATTACHED, identity)
        assert decision is Decision.DENY
        assert "no puede cambiar de proceso" in reason


def test_attached_tool_without_process_is_denied_with_recovery_hint() -> None:
    decision, reason = AgentPolicy().evaluate(_tool(attached=True), FlowState.NO_PROCESS, None)

    assert decision is Decision.DENY
    assert "seleccione un proceso" in reason


def test_autonomous_identity_mismatch_disables_mode_immediately() -> None:
    bound = _identity()
    policy = AgentPolicy(mode=AgentMode.AUTONOMOUS, bound_identity=bound)

    decision, reason = policy.evaluate(_tool(), FlowState.ATTACHED, _identity(created=2.0))

    assert decision is Decision.DENY
    assert "desactivó" in reason
    assert policy.mode is AgentMode.GUIDED
    assert policy.bound_identity is None


def test_guided_mutation_requires_confirmation() -> None:
    decision, reason = AgentPolicy().evaluate(_tool(mutating=True), FlowState.ATTACHED, _identity())

    assert decision is Decision.CONFIRM
    assert "confirmación" in reason


def test_autonomous_mutations_consume_limit_then_deny() -> None:
    identity = _identity()
    policy = AgentPolicy(
        mode=AgentMode.AUTONOMOUS,
        write_limit=2,
        writes_used=0,
        bound_identity=identity,
    )
    tool = _tool(mutating=True)

    assert policy.evaluate(tool, FlowState.ATTACHED, identity)[0] is Decision.ALLOW
    assert policy.evaluate(tool, FlowState.ATTACHED, identity)[0] is Decision.ALLOW
    decision, reason = policy.evaluate(tool, FlowState.ATTACHED, identity)

    assert decision is Decision.DENY
    assert policy.writes_used == 2
    assert "Límite de 2" in reason


def test_tool_outside_allowed_flow_state_is_denied() -> None:
    decision, reason = AgentPolicy().evaluate(
        _tool(states=frozenset({FlowState.NARROWED})),
        FlowState.ATTACHED,
        _identity(),
    )

    assert decision is Decision.DENY
    assert FlowState.NARROWED.value in reason
