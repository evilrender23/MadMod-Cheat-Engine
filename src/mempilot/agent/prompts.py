"""Spanish system instructions and authoritative runtime state rendering."""

from __future__ import annotations

from collections.abc import Sequence

from mempilot.agent.policies import AgentMode, AgentPolicy, FlowState
from mempilot.controller import ScanStatus
from mempilot.core.backend import ProcessIdentity
from mempilot.core.watcher import WatchEntry

SYSTEM_PROMPT = """Eres el asistente de M@D-Engine para inspección autorizada de memoria local.
Solo puedes observar o actuar mediante las herramientas tipadas que M@D-Engine publica. Nunca
inventes direcciones, valores, procesos, resultados ni permisos, y nunca sugieras evasión,
inyección, drivers, anti-cheat o código arbitrario.

Sigue el estado [ESTADO] que aparece al principio de cada turno: es la única fuente de verdad
sobre el proceso, el escaneo y la vigilancia. Si el tipo de un valor es desconocido, propón
probar int32 y float32 por separado. Después de un primer escaneo con muchos candidatos, pide
al usuario que provoque un cambio observable y espera a que indique el nuevo valor antes de
refinar. No refines suponiendo un cambio que el usuario no confirmó. Con cinco candidatos o
menos, muestra los hallazgos, añádelos a vigilancia cuando corresponda y pide confirmación
antes de escribir o congelar en modo guiado.

No cambies de proceso por iniciativa propia. No escribas, congeles ni cargues un workspace sin
respetar la decisión de seguridad devuelta por M@D-Engine. Para crear un trainer, encuentra una
dirección, añádela a vigilancia, aplica el valor de prueba y pide al usuario que compruebe el
efecto. Solo llama a save_trainer_trick después de que el usuario confirme explícitamente que
funciona; explica si la dirección guardada es absoluta y puede cambiar al reiniciar el proceso.
Si una herramienta devuelve ok=false, explica el error en español y propone el siguiente paso
recuperable; no repitas la misma llamada sin corregir su causa. Responde de forma breve,
concreta y siempre en español.
"""


def state_line(
    identity: ProcessIdentity | None,
    write_access: bool,
    flow_state: FlowState,
    scan: ScanStatus,
    watches: Sequence[WatchEntry],
    policy: AgentPolicy,
) -> str:
    """Render the literal, compact state item prepended before every provider call."""
    if identity is None:
        process_name = "ninguno"
        pid = "-"
        architecture = "-"
    else:
        process_name = identity.name
        pid = str(identity.pid)
        architecture = identity.architecture.value

    data_type = scan.data_type.value if scan.data_type is not None else "ninguna"
    scan_mode = scan.last_mode.value if scan.last_mode is not None else "ninguno"
    frozen = sum(1 for watch in watches if watch.frozen)
    if policy.mode is AgentMode.AUTONOMOUS:
        agent = f"autónomo {policy.writes_used}/{policy.write_limit}"
    elif policy.mode is AgentMode.OFF:
        agent = "desactivado"
    else:
        agent = "guiado"
    return (
        f"[ESTADO] proceso={process_name} pid={pid} arch={architecture} "
        f"escritura={'sí' if write_access else 'no'} | paso={flow_state.value} | "
        f"sesión={data_type} modo={scan_mode} candidatos={scan.candidates} | "
        f"vigilancia={len(watches)} congelados={frozen} | agente={agent}"
    )
