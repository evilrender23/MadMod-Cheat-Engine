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
    "lab.window_title": "Memory Lab — PID {pid}",
    "lab.description": (
        "Proceso de laboratorio para practicar lecturas, escaneos, escrituras y congelado."
    ),
    "lab.column.name": "Nombre",
    "lab.column.type": "Tipo",
    "lab.column.value": "Valor",
    "lab.column.address": "Dirección",
    "lab.damage": "Recibir daño (-27)",
    "lab.heal": "Curar (+15)",
    "lab.spend_coins": "Gastar monedas (-50)",
    "lab.add_coins": "Añadir monedas (+100)",
    "lab.speed_up": "Velocidad +0.25",
    "lab.speed_down": "Velocidad -0.25",
    "lab.toggle_alive": "Alternar alive",
    "lab.restore": "Restaurar todo",
    "lab.auto_stamina": "Stamina decreciente automática",
    "lab.log_label": "Registro de acciones",
    "lab.log.damage": "Daño recibido: salud = {value}",
    "lab.log.heal": "Curación aplicada: salud = {value}",
    "lab.log.spend_coins": "Monedas gastadas: monedas = {value}",
    "lab.log.add_coins": "Monedas añadidas: monedas = {value}",
    "lab.log.speed_up": "Velocidad aumentada: velocidad = {value}",
    "lab.log.speed_down": "Velocidad reducida: velocidad = {value}",
    "lab.log.toggle_alive": "Estado alive alternado: {value}",
    "lab.log.restore": "Todos los valores se restauraron.",
    "lab.log.auto_stamina_on": "Descenso automático de stamina activado.",
    "lab.log.auto_stamina_off": "Descenso automático de stamina desactivado.",
    "lab.value.true": "Sí",
    "lab.value.false": "No",
    "lab.actions": "Acciones",
    "lab.table_accessible": "Variables y direcciones del laboratorio",
}


def t(key: str, **kw: object) -> str:
    """Translate a key and interpolate named values."""
    return STRINGS[key].format(**kw)
