"""Central Spanish user-interface strings."""

STRINGS: dict[str, str] = {
    "app.name": "MemPilot",
    "app.version": "Versión {version}",
    "action.attach": "Seleccionar proceso…",
    "action.detach": "Desacoplar",
    "action.settings": "Ajustes",
    "action.memory_lab": "Iniciar Memory Lab",
    "action.cancel": "Cancelar",
    "action.first_scan": "Primer escaneo",
    "action.next_scan": "Siguiente escaneo",
    "action.reset": "Reiniciar",
    "action.save_workspace": "Guardar workspace…",
    "action.load_workspace": "Cargar workspace…",
    "status.disconnected": "Sin proceso",
    "status.connected": "Conectado",
    "status.read_only": "Solo lectura",
    "status.read_write": "Lectura-escritura",
    "status.scanning": "Escaneando…",
    "status.ready": "Listo",
    "scan.too_many": (
        "Demasiados candidatos (>{count}). Usa un valor más específico "
        "o reduce el rango de regiones."
    ),
    "scan.unknown_skipped": (
        "Se omitieron {count} regiones (límite de {limit} MB). Auméntalo en Ajustes → Escaneo."
    ),
    "agent.disabled": "IA desactivada — configura la clave en Ajustes → IA",
    "agent.autonomous": "MODO AUTÓNOMO ACTIVO — proceso {name} (PID {pid})",
    "error.title": "No se pudo completar la operación",
    "error.details": "Detalles",
    "error.copy": "Copiar detalles",
}


def t(key: str, **kw: object) -> str:
    """Translate a key and interpolate named values."""
    return STRINGS[key].format(**kw)
