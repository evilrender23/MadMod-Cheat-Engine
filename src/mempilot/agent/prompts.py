"""Language-aware agent instructions and authoritative runtime state rendering."""

from __future__ import annotations

from collections.abc import Sequence

from mempilot.agent.policies import AgentMode, AgentPolicy, FlowState
from mempilot.controller import ScanStatus
from mempilot.core.backend import ProcessIdentity
from mempilot.core.watcher import WatchEntry
from mempilot.i18n import Language, architecture_label, get_language

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

_ENGLISH_SYSTEM_PROMPT = """You are the M@D-Engine assistant for authorized local memory inspection.
You may only observe or act through the typed tools published by M@D-Engine. Never invent
addresses, values, processes, results, or permissions, and never suggest evasion, injection,
drivers, anti-cheat bypasses, or arbitrary code.

Follow the [STATE] item at the beginning of every turn: it is the sole source of truth about the
process, scan, and watch list. If a value's type is unknown, suggest trying int32 and float32
separately. After an initial scan with many candidates, ask the user to cause an observable change
and wait for the new value before refining. Never assume an unconfirmed change. With five or fewer
candidates, show the findings, add them to the watch list when appropriate, and request
confirmation before writing or freezing in guided mode.

Do not switch processes on your own. Do not write, freeze, or load a workspace without respecting
the security decision returned by M@D-Engine. To create a trainer, find an address, add it to the
watch list, apply the test value, and ask the user to verify the effect. Only call
save_trainer_trick after the user explicitly confirms it works; explain when a saved absolute
address may change after restarting the process. If a tool returns ok=false, explain the error in
English and propose the next recoverable step; do not repeat the same call without correcting its
cause. Always respond briefly, concretely, and in English.
"""


def system_prompt() -> str:
    """Return agent instructions in the active interface language."""
    return _ENGLISH_SYSTEM_PROMPT if get_language() is Language.ENGLISH else SYSTEM_PROMPT


def state_line(
    identity: ProcessIdentity | None,
    write_access: bool,
    flow_state: FlowState,
    scan: ScanStatus,
    watches: Sequence[WatchEntry],
    policy: AgentPolicy,
) -> str:
    """Render the literal, compact state item prepended before every provider call."""
    english = get_language() is Language.ENGLISH
    if identity is None:
        process_name = "none" if english else "ninguno"
        pid = "-"
        architecture = "-"
    else:
        process_name = identity.name
        pid = str(identity.pid)
        architecture = architecture_label(identity.architecture.value)

    data_type = (
        scan.data_type.value if scan.data_type is not None else ("none" if english else "ninguna")
    )
    scan_mode = (
        scan.last_mode.value if scan.last_mode is not None else ("none" if english else "ninguno")
    )
    frozen = sum(1 for watch in watches if watch.frozen)
    if policy.mode is AgentMode.AUTONOMOUS:
        agent = (
            f"autonomous {policy.writes_used}/{policy.write_limit}"
            if english
            else f"autónomo {policy.writes_used}/{policy.write_limit}"
        )
    elif policy.mode is AgentMode.OFF:
        agent = "disabled" if english else "desactivado"
    else:
        agent = "guided" if english else "guiado"
    if english:
        return (
            f"[STATE] process={process_name} pid={pid} arch={architecture} "
            f"write={'yes' if write_access else 'no'} | step={flow_state.value} | "
            f"session={data_type} mode={scan_mode} candidates={scan.candidates} | "
            f"watches={len(watches)} frozen={frozen} | agent={agent}"
        )
    return (
        f"[ESTADO] proceso={process_name} pid={pid} arch={architecture} "
        f"escritura={'sí' if write_access else 'no'} | paso={flow_state.value} | "
        f"sesión={data_type} modo={scan_mode} candidatos={scan.candidates} | "
        f"vigilancia={len(watches)} congelados={frozen} | agente={agent}"
    )
