"""Runtime-selectable Spanish and English user-interface strings."""

from enum import StrEnum

from mempilot.i18n_en import ENGLISH_STRINGS

STRINGS: dict[str, str] = {
    "app.name": "M@D-Engine",
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
    "agent.disabled": "IA desactivada — configura una CLI compatible en Ajustes → IA",
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
    "ui.help": "Ayuda",
    "ui.close": "Cerrar",
    "ui.refresh": "Actualizar",
    "ui.yes": "Sí",
    "ui.no": "No",
    "top.process_summary": "PID {pid} · {name} · {arch}",
    "top.disconnected_summary": "Ningún proceso seleccionado",
    "top.connection_accessible": "Estado de conexión: {state}",
    "top.process_accessible": "Proceso seleccionado",
    "process.title": "Seleccionar proceso",
    "process.search": "Buscar por nombre o PID",
    "process.show_system": "Mostrar procesos del sistema",
    "process.refresh": "Actualizar procesos",
    "process.loading": "Buscando procesos…",
    "process.empty": "No se encontraron procesos. Cambia el filtro o actualiza la lista.",
    "process.attach_read": "Adjuntar en solo lectura",
    "process.attach_write": "Adjuntar con escritura",
    "process.write_warning": (
        "El permiso de escritura permite modificar la memoria del proceso seleccionado."
    ),
    "process.column.name": "Proceso",
    "process.column.pid": "PID",
    "process.column.arch": "Arquitectura",
    "process.column.user": "Usuario",
    "process.column.path": "Ruta",
    "process.column.note": "Estado",
    "process.table_accessible": "Procesos locales disponibles",
    "scan.data_type": "Tipo de dato",
    "scan.condition": "Condición",
    "scan.value": "Valor",
    "scan.value2": "Valor 2",
    "scan.use_tolerance": "Usar tolerancia",
    "scan.tolerance": "Tolerancia",
    "scan.case_sensitive": "Distinguir mayúsculas",
    "scan.regions": "Regiones",
    "scan.writable_only": "Solo escribibles",
    "scan.include_image": "Incluir imagen",
    "scan.include_mapped": "Incluir mapeadas",
    "scan.alignment": "Alineación",
    "scan.alignment.auto": "Automática",
    "scan.alignment.byte": "1 byte",
    "scan.address_min": "Dirección mínima",
    "scan.address_max": "Dirección máxima",
    "scan.statistics": "Estadísticas",
    "scan.stat.candidates": "Candidatos",
    "scan.stat.regions": "Regiones analizadas",
    "scan.stat.bytes": "Bytes analizados",
    "scan.stat.duration": "Última duración",
    "scan.stat.refinements": "Refinamientos",
    "scan.stat.last": "Última pasada",
    "scan.validation.required": "Introduce un valor para esta condición.",
    "scan.validation.value2": "Introduce el límite superior.",
    "scan.validation.address": "Usa una dirección hexadecimal válida.",
    "scan.validation.tolerance": "Introduce una tolerancia mayor o igual que cero.",
    "scan.validation.ready": "Corrige el valor antes de iniciar el escaneo.",
    "scan.mode.exact": "Valor exacto",
    "scan.mode.unknown_initial": "Valor desconocido inicial",
    "scan.mode.changed": "Valor cambiado",
    "scan.mode.unchanged": "Valor sin cambios",
    "scan.mode.increased": "Valor aumentado",
    "scan.mode.decreased": "Valor disminuido",
    "scan.mode.increased_by": "Aumentado en",
    "scan.mode.decreased_by": "Disminuido en",
    "scan.mode.between": "Entre",
    "scan.mode.greater_than": "Mayor que",
    "scan.mode.less_than": "Menor que",
    "scan.mode.aob": "Patrón AOB",
    "scan.mode.text": "Texto",
    "data_type.int8": "Int8",
    "data_type.int16": "Int16",
    "data_type.int32": "Int32",
    "data_type.int64": "Int64",
    "data_type.uint8": "UInt8",
    "data_type.uint16": "UInt16",
    "data_type.uint32": "UInt32",
    "data_type.uint64": "UInt64",
    "data_type.float32": "Float32",
    "data_type.float64": "Float64",
    "data_type.bool": "Bool",
    "data_type.string_utf8": "Texto UTF-8",
    "data_type.string_utf16": "Texto UTF-16 LE",
    "data_type.aob": "AOB",
    "data_type.bytes": "Bytes",
    "results.column.address": "Dirección",
    "results.column.value": "Valor",
    "results.column.previous": "Anterior",
    "results.column.type": "Tipo",
    "results.column.region": "Región/Módulo",
    "results.column.protection": "Protección",
    "results.column.changes": "Cambios",
    "results.column.read": "L",
    "results.column.write": "E",
    "results.table_accessible": "Resultados del escaneo",
    "results.empty": "Ejecuta un primer escaneo para ver candidatos.",
    "results.no_matches": "Ningún candidato coincide con el filtro actual.",
    "results.filter": "Filtrar dirección, valor o región",
    "results.module": "Todos los módulos",
    "results.previous_page": "Página anterior",
    "results.next_page": "Página siguiente",
    "results.page_jump": "Ir a página",
    "results.range": "{first}–{last} de {total}",  # noqa: RUF001 - typographic range
    "results.range_empty": "0 de 0",
    "results.action.add_watch": "Añadir a vigilancia",
    "results.action.edit": "Editar valor…",
    "results.action.copy_address": "Copiar dirección",
    "results.action.copy_value": "Copiar valor",
    "results.action.reinterpret": "Cambiar interpretación",
    "results.action.label": "Etiquetar…",
    "results.action.delete": "Eliminar candidatos",
    "results.edit.title": "Editar valor",
    "results.edit.prompt": "Nuevo valor para {address}:",
    "results.label.title": "Etiquetar resultado",
    "results.label.prompt": "Etiqueta:",
    "results.unsupported_local_action": (
        "Esta acción solo afecta a la vista actual y no modifica la memoria."
    ),
    "status.progress_accessible": "Progreso del escaneo",
    "status.metrics": ("regiones {done}/{total} · {megabytes} MB · {speed} MB/s · {elapsed} s"),
    "status.cancelled": "Escaneo cancelado. Puedes iniciar uno nuevo.",
    "status.failed": "El escaneo no pudo completarse.",
    "status.scan_complete": "Escaneo completado: {count} candidatos.",
    "status.workspace_saved": "Workspace guardado en {path}.",
    "status.workspace_loaded": "Workspace cargado desde {path}.",
    "status.process_lost": "El proceso PID {pid} terminó.",
    "chat.title": "Asistente",
    "chat.history_accessible": "Historial de conversación y actividad",
    "chat.mode": "Modo",
    "chat.mode.guided": "Guiado",
    "chat.mode.autonomous": "Autónomo",
    "chat.writes": "Escrituras {used}/{limit}",
    "chat.input": "Escribe una consulta para el asistente",
    "chat.send": "Enviar",
    "chat.trainer_creator": "Crear trainer con IA",
    "chat.trainer_prompt": (
        "Quiero crear un trainer para el proceso actual. Guíame para encontrar y probar "
        "un truco, y ofréceme guardarlo solo después de que confirme que funciona."
    ),
    "chat.disabled_help": (
        "La inspección manual sigue disponible. Instala e inicia sesión en Antigravity CLI, "
        "Codex CLI o Claude Code y selecciónala en Ajustes → IA."
    ),
    "chat.offline_reply": (
        "La IA está desactivada. Puedes seguir usando escaneos, resultados y vigilancia."
    ),
    "chat.activity_count": "Actividad ({count})",
    "chat.activity_expand": "Mostrar actividad",
    "chat.activity_collapse": "Ocultar actividad",
    "chat.user": "Tú",
    "chat.agent": "Asistente",
    "chat.thinking": "Pensando…",
    "overlay.title": "M@D-Engine Overlay",
    "overlay.hide": "Ocultar",
    "overlay.hotkey_hint": "Ocultar: Pause, Ctrl+Shift+º o Esc",
    "overlay.history": "Conversación del overlay",
    "overlay.chat_input": "Habla con M@D-Engine",
    "overlay.no_process": "No hay un proceso adjunto.",
    "overlay.process": "{name} · PID {pid} · {access}",
    "overlay.manual": "Ajustes manuales",
    "overlay.trainers": "Trucos guardados",
    "overlay.trainer": "Truco",
    "overlay.no_trainers": "Aún no hay trucos guardados para {name}.",
    "overlay.trainer_info": "Tipo: {type} · Modo: {mode} · Estado: {state}",
    "overlay.trainer.active": "activo",
    "overlay.trainer.inactive": "inactivo",
    "overlay.trainer.mode.freeze": "congelado",
    "overlay.trainer.mode.write_pair": "valor reversible",
    "overlay.trainer.activate": "Activar",
    "overlay.trainer.deactivate": "Desactivar",
    "overlay.trainer.activate_confirm": "Activar el truco guardado «{name}»",
    "overlay.trainer.deactivate_confirm": "Desactivar el truco guardado «{name}»",
    "overlay.trainer.activated": "Truco activado.",
    "overlay.trainer.deactivated": "Truco desactivado.",
    "overlay.trainer.enabled_value": "Valor al activar",
    "overlay.trainer.disabled_value": "Valor al desactivar",
    "overlay.trainer.save_values": "Guardar valores",
    "overlay.trainer.values_saved": "Valores del truco guardados.",
    "overlay.trainer.edit_inactive": "Desactiva el truco para editar sus valores.",
    "overlay.trainer.create_manual": "Crear trainer con esta vigilancia…",
    "overlay.watch": "Vigilancia",
    "overlay.value": "Valor nuevo o deseado",
    "overlay.no_watches": "Añade una dirección a vigilancia desde M@D-Engine para ajustarla aquí.",
    "overlay.watch_info": "Tipo: {type} · Actual: {current} · Congelado: {frozen}",
    "overlay.yes": "sí",
    "overlay.no": "no",
    "overlay.write": "Escribir",
    "overlay.freeze": "Congelar",
    "overlay.unfreeze": "Descongelar",
    "overlay.read_only": "Vuelve a adjuntar el proceso con permiso de escritura.",
    "overlay.write_confirm": "Escribir una vigilancia desde el overlay",
    "overlay.freeze_confirm": "Congelar una vigilancia desde el overlay",
    "overlay.write_ok": "Valor escrito correctamente.",
    "overlay.freeze_ok": "Vigilancia congelada.",
    "overlay.unfreeze_ok": "Vigilancia descongelada.",
    "overlay.hotkey_failed": "No se pudo registrar el atajo global: {shortcuts}.",
    "overlay.hotkey_ready": "Overlay disponible desde {name}: Pause o Ctrl+Shift+º.",
    "chat.autonomous.title": "Activar modo autónomo",
    "chat.autonomous.permissions": (
        "Permisos concedidos para {name} (PID {pid}):\n"
        "• Escribir en {name}.\n"
        "• Congelar valores.\n"
        "• Máximo {limit} escrituras.\n"
        "• No puede cambiar de proceso ni ampliar permisos."
    ),
    "chat.autonomous.consent": "Entiendo y concedo estos permisos para este proceso.",
    "chat.autonomous.needs_process": (
        "Selecciona primero un proceso. El permiso autónomo queda vinculado a su identidad."
    ),
    "settings.title": "Ajustes",
    "settings.scan_tab": "Escaneo",
    "settings.ui_tab": "Interfaz",
    "settings.ai_tab": "IA",
    "settings.unknown_budget": "Memoria para valor desconocido (MB)",
    "settings.max_candidates": "Máximo de candidatos",
    "settings.results_page_size": "Resultados por página",
    "settings.results_refresh": "Refresco de resultados (ms)",
    "settings.watch_refresh": "Refresco de vigilancia (ms)",
    "settings.show_system": "Mostrar procesos del sistema",
    "settings.ai_enabled": "Activar asistente de IA",
    "settings.provider": "Proveedor CLI",
    "settings.executable": "Ejecutable opcional",
    "settings.executable_hint": "Vacío: buscar agy, codex o claude en PATH",
    "settings.cli_status": "Estado",
    "settings.cli_found": "CLI detectada: {path}",
    "settings.cli_missing": "No se encontró «{command}» en PATH.",
    "settings.model": "Modelo opcional",
    "settings.model_hint": "Vacío: usar el modelo predeterminado de la CLI",
    "settings.timeout": "Tiempo de espera (s)",
    "settings.write_limit": "Límite de escrituras autónomas",
    "settings.save": "Guardar ajustes",
    "settings.saved": "Los ajustes se guardaron.",
    "settings.language": "Idioma",
    "settings.language.es": "Español",
    "settings.language.en": "Inglés",
    "settings.language_restart": (
        "Idioma guardado. Reinicia M@D-Engine para aplicarlo a toda la interfaz."
    ),
    "confirm.title": "Confirmar escritura",
    "confirm.action": "Acción",
    "confirm.address": "Dirección",
    "confirm.type": "Tipo",
    "confirm.change": "Cambio",
    "confirm.remember": "No volver a preguntar en esta sesión",
    "confirm.accept": "Confirmar",
    "confirm.reject": "Rechazar",
    "confirm.manual_write": "Escribir memoria manualmente",
    "error.technical": "Causa técnica",
    "error.unknown": "Se produjo un error inesperado. Inténtalo de nuevo.",
    "error.process_not_found": (
        "El proceso ya no existe. Actualiza la lista y selecciona otro proceso."
    ),
    "error.process_not_allowed": (
        "Ese proceso está protegido. Selecciona un proceso de usuario autorizado."
    ),
    "error.access_denied": (
        "Acceso denegado. Usa un proceso de tu nivel de integridad o ejecuta como administrador."
    ),
    "error.process_exited": "El proceso terminó. Vuelve a seleccionarlo si lo inicias de nuevo.",
    "error.not_attached": (
        "No hay ningún proceso adjunto. Selecciona un proceso antes de continuar."
    ),
    "error.write_not_permitted": (
        "La sesión es de solo lectura. Vuelve a adjuntarte con permiso de escritura."
    ),
    "error.memory_read": (
        "No se pudo leer la memoria. Comprueba que el proceso siga activo "
        "y la dirección sea válida."
    ),
    "error.memory_write": (
        "No se pudo escribir la memoria. Comprueba el permiso y la protección de la región."
    ),
    "error.invalid_address": (
        "La dirección no pertenece a una región válida. Actualiza los resultados "
        "e inténtalo de nuevo."
    ),
    "error.value_parse": "El valor no tiene el formato esperado para el tipo seleccionado.",
    "error.pattern": "El patrón AOB no es válido. Usa bytes hexadecimales y ?? para comodines.",
    "error.scan": "El escaneo no pudo completarse. Reduce el rango o usa un valor más específico.",
    "error.scan_cancelled": "El escaneo fue cancelado. Puedes iniciar uno nuevo.",
    "error.workspace": "El workspace no es válido. Comprueba el archivo o crea uno nuevo.",
    "error.trainer": "El trainer no es válido. Comprueba el proceso y los trucos guardados.",
    "error.policy_denied": (
        "La política de seguridad impide esta operación. Revisa el modo y los permisos del agente."
    ),
    "error.provider": (
        "El proveedor de IA no respondió correctamente. Revisa la conexión y la configuración."
    ),
    "scan.validation.alignment_negative": (
        "La alineación no puede ser negativa. Usa Automática o 1 byte."
    ),
    "scan.validation.chunk_positive": "El tamaño de bloque debe ser mayor que cero.",
    "scan.validation.candidates_positive": ("El límite de candidatos debe ser mayor que cero."),
    "scan.validation.budget_nonnegative": "El presupuesto de memoria no puede ser negativo.",
    "scan.validation.range": "El rango de direcciones no es válido. Corrige sus límites.",
    "scan.validation.bytes": "Bytes es un formato de visualización y no se puede escanear.",
    "scan.validation.aob_type": "La condición AOB requiere el tipo de dato AOB.",
    "scan.validation.aob_mode": "El tipo AOB solo admite la condición AOB.",
    "scan.validation.text_type": ("La condición Texto requiere un tipo de texto UTF-8 o UTF-16."),
    "scan.validation.text_mode": "Los tipos de texto solo admiten la condición Texto.",
    "scan.validation.numeric_type": "Esta condición requiere un tipo numérico.",
    "scan.validation.valueless": "Esta condición no admite un valor de búsqueda.",
    "scan.validation.value2_only": "Valor 2 solo se usa con la condición Entre.",
    "scan.validation.between_order": ("El límite inferior de Entre no puede superar al superior."),
    "value.fixed_size": "{type} no tiene tamaño fijo.",
    "value.overflow": "El valor {value} desborda el rango de {type} ({low} a {high}).",
    "value.invalid": "No se puede interpretar {value} como {type}. Corrige el valor.",
    "value.unknown_type": "Tipo de dato desconocido: {type}.",
    "value.decode_size": "Se necesitan {size} bytes para decodificar {type}.",
    "aob.empty": "El patrón AOB está vacío. Escribe al menos un byte hexadecimal.",
    "aob.wildcard_size": "Los comodines AOB deben ocupar un byte completo: ? o ??.",
    "aob.even_digits": "El patrón hexadecimal debe contener pares de dígitos.",
    "aob.token_pair": "Token AOB inválido: {token}. Usa pares hexadecimales.",
    "aob.token_hex": "Token AOB inválido: {token}. Usa 00-FF o ??.",
    "address.negative": "Una dirección no puede ser negativa.",
    "workspace.save_title": "Guardar workspace",
    "workspace.load_title": "Cargar workspace",
    "agent.operation_cancelled": "Operación del agente cancelada.",
    "agent.tool_timeout": "La herramienta agotó el tiempo de espera.",
    "results.page_size_positive": "El tamaño de página de resultados debe ser positivo.",
    "results.visible_expected": "Se esperaba una página visible de resultados.",
    "watch.resolve_failed": "No se pudo resolver la dirección.",
    "watch.read_failed": "No se pudo leer la dirección vigilada.",
    "watch.freeze_tick_limit": (
        "Se alcanzó el límite de 32 escrituras de congelado por ciclo. "
        "Reduce las vigilancias congeladas o aumenta sus intervalos."
    ),
    "error.agent_bound_process": (
        "El agente está vinculado a otro proceso. Pide al usuario que seleccione el proceso."
    ),
    "status.process_changed": "Se cambió el proceso adjunto.",
    "error.process_changed_during_attach": (
        "El proceso cambió mientras se abría. Actualiza la lista y vuelve a intentarlo."
    ),
    "error.scan_session_process": "La sesión pertenece a otro proceso. Inicia un nuevo escaneo.",
    "error.refine_type": "El tipo del refinamiento debe coincidir con el escaneo inicial.",
    "error.reset_while_scanning": "Cancela el escaneo en curso antes de reiniciar la sesión.",
    "error.partial_write": (
        "Solo se escribieron {written} de {expected} bytes. Actualiza la dirección."
    ),
    "error.watch_partial_write": "La escritura de la vigilancia quedó incompleta.",
    "error.trainer_resolve": "No se pudo resolver la dirección del truco.",
    "error.lab_exited": "Memory Lab terminó antes de mostrar su ventana.",
    "error.lab_window_timeout": "Memory Lab no mostró una ventana dentro de 10 segundos.",
    "error.agent_busy": "Ya hay una operación del agente en curso.",
    "status.process_detached_on_exit": "El proceso terminó y M@D-Engine se desacopló.",
    "error.pid_exited": "El proceso PID {pid} terminó. Selecciona otro proceso para continuar.",
    "error.scan_busy": "Ya hay un escaneo en curso. Cancélalo antes de iniciar otro.",
    "error.refine_incompatible": "El refinamiento devolvió un resultado incompatible.",
    "watch.address_mode_invalid": (
        "La vigilancia debe usar una dirección absoluta, módulo+offset o cadena de punteros."
    ),
    "watch.address_negative": "La dirección de vigilancia no puede ser negativa.",
    "watch.module_offset_pair": "El módulo y el offset deben indicarse juntos.",
    "watch.module_name_required": "El nombre del módulo no puede estar vacío.",
    "watch.interval_range": "El intervalo de vigilancia debe estar entre 50 y 5000 ms.",
    "watch.name_required": "El nombre de la vigilancia no puede estar vacío.",
    "watch.module_not_loaded": "El módulo {module} no está cargado.",
    "watch.offset_negative": "El offset produce una dirección negativa.",
    "pointer.module_not_loaded": "módulo {module} no cargado",
    "process.pid_protected": (
        "El PID {pid} está protegido. Selecciona un proceso de usuario autorizado."
    ),
    "process.name_protected": (
        "El proceso {name} (PID {pid}) está protegido. Selecciona un proceso de usuario autorizado."
    ),
    "process.pid_finished": "El PID {pid} terminó durante la consulta. Actualiza la lista.",
    "memory.read_size_negative": "El tamaño de lectura no puede ser negativo.",
    "memory.read_address": ("No se pudo leer la dirección {address}. Comprueba que siga asignada."),
    "memory.buffer_writable": "El búfer de lectura debe ser modificable.",
    "memory.region_not_writable": (
        "La dirección {address} no pertenece a una región asignada y escribible. "
        "Actualiza los resultados e inténtalo de nuevo."
    ),
    "memory.write_address": (
        "No se pudo escribir la dirección {address}. "
        "Comprueba la protección de la región y vuelve a intentarlo."
    ),
    "pointer.read_failed_at": "lectura fallida en {address}",
    "pointer.read_failed": "lectura fallida",
    "pointer.partial_read": "lectura parcial",
    "pointer.null": "puntero nulo",
    "pointer.null_at_step": "puntero nulo en el paso {step}",
    "pointer.resolved": "resuelto",
    "process.pid_missing": (
        "El PID {pid} ya no existe. Actualiza la lista y selecciona otro proceso."
    ),
    "process.pid_uncheckable": (
        "No se puede comprobar el PID {pid}. Selecciona un proceso de usuario autorizado."
    ),
    "policy.ai_off": "La IA está desactivada. Actívala en Ajustes → IA.",
    "policy.autonomous_process": "El modo autónomo no puede cambiar de proceso.",
    "policy.select_process": "Pide al usuario que seleccione un proceso.",
    "policy.identity_changed": (
        "El proceso ya no coincide con la autorización. Se desactivó el modo autónomo; "
        "pide al usuario que lo autorice de nuevo."
    ),
    "policy.confirm_trainer": "El usuario debe confirmar que el truco funciona.",
    "policy.confirm_action": "Esta acción requiere confirmación del usuario.",
    "policy.write_limit": (
        "Límite de {limit} escrituras alcanzado; el usuario debe ampliarlo en Ajustes."
    ),
    "policy.autonomous_allowed": "Acción autorizada dentro del límite de escrituras.",
    "policy.state_denied": (
        "La herramienta no está disponible en el paso {state}. "
        "Completa antes el paso adecuado: {expected}."
    ),
    "policy.read_allowed": "Acción de solo lectura autorizada.",
    "policy.follow_hint": "Sigue el paso indicado por la política.",
    "confirmation.rejected_error": "El usuario rechazó la confirmación.",
    "confirmation.rejected_hint": ("No repitas la escritura sin una nueva indicación del usuario."),
    "confirmation.timeout_error": "Confirmación expirada.",
    "confirmation.timeout_hint": "Pregunta al usuario si desea volver a intentarlo.",
    "confirmation.unknown": "desconocido",
    "confirmation.watch_detail": "{action}: {label}\nValor actual: {current}\nValor nuevo: {value}",
    "confirmation.trainer_detail": (
        "¿Confirmas que el truco funciona y quieres guardarlo?\n"
        "Proceso: {process}\nTruco: {name}\nActivado: {enabled}\nDesactivado: {disabled}"
    ),
    "confirmation.unfreeze": "descongelar",
    "confirmation.attach_detail": (
        "Adjuntar al PID {pid} con permiso de escritura: {write_access}"
    ),
    "confirmation.workspace_detail": "Cargar workspace: {name}",
    "agent.request_failed": (
        "El agente no pudo completar la solicitud. Revisa el estado e inténtalo de nuevo."
    ),
    "provider.executable_required": "La ruta del ejecutable CLI no puede estar vacía.",
    "provider.invalid_json_args": (
        "{provider} devolvió argumentos JSON inválidos para {tool}. Inténtalo de nuevo."
    ),
    "provider.unstructured_args": (
        "{provider} devolvió argumentos no estructurados para {tool}. Inténtalo de nuevo."
    ),
    "provider.timeout": (
        "{provider} no respondió en {seconds} s. Aumenta el tiempo de espera en Ajustes → IA."
    ),
    "provider.start_failed": "No se pudo iniciar {provider}. Comprueba la ruta en Ajustes → IA.",
    "provider.exit_code": "{provider} terminó con el código {code}. {hint}",
    "provider.empty_response": (
        "{provider} no produjo una respuesta. Comprueba que la sesión esté iniciada "
        "y que el modelo seleccionado admita salida estructurada."
    ),
    "provider.request_too_large": (
        "La petición actual es demasiado grande para Antigravity CLI. "
        "Usa un mensaje más breve o solicita menos resultados."
    ),
    "provider.incompatible_response": (
        "{provider} devolvió una respuesta incompatible. "
        "Comprueba el modelo seleccionado e inténtalo de nuevo."
    ),
    "provider.login_hint": "Inicia sesión directamente con «{provider}» y vuelve a intentarlo.",
    "provider.failure_hint": (
        "Comprueba la instalación, la sesión iniciada y el modelo en Ajustes → IA."
    ),
    "freezer.limit_positive": "El límite de escrituras por ciclo debe ser positivo.",
    "results.offset_limit_nonnegative": ("El desplazamiento y el límite no pueden ser negativos."),
    "scan.delta_required": "Esta comparación requiere un delta.",
    "scan.comparison_unsupported": "Modo de comparación no compatible: {mode}.",
    "scan.pattern_mask_length": ("El patrón y la máscara deben tener la misma longitud no nula."),
    "scan.first_numeric_invalid": ("Esta condición no es válida para un primer escaneo numérico."),
    "scan.refine_invalid": "La condición no es válida para este refinamiento.",
    "scan.variable_invalid": "La condición no es válida para datos de longitud variable.",
    "scan.unknown_refine_numeric": (
        "Un escaneo de valor desconocido debe refinarse con una comparación numérica."
    ),
    "audit.write_count_nonnegative": "El número de escrituras no puede ser negativo.",
    "trainer.name_required": "El nombre del truco no puede estar vacío.",
    "trainer.address_ambiguous": (
        "La dirección persistida del truco es ambigua o está incompleta."
    ),
    "trainer.disabled_required": (
        "Un truco de escritura reversible necesita un valor desactivado."
    ),
    "trainer.saved_invalid": ("El trainer guardado no es válido o usa una versión incompatible."),
    "trainer.wrong_process": "El trainer guardado pertenece a otro proceso.",
    "trainer.trick_invalid": (
        "El truco no es válido. Revisa el nombre, la dirección y los valores."
    ),
    "trainer.values_invalid": (
        "Los valores del truco no son válidos. Revisa el valor activado y desactivado."
    ),
    "workspace.version_invalid": (
        "El workspace no es válido o usa una versión incompatible. "
        "Selecciona un archivo de esquema 1 o crea uno nuevo."
    ),
    "trainer.architecture_mismatch": (
        "La arquitectura del trainer no coincide con el proceso adjunto."
    ),
    "trainer.missing": "No existe el truco guardado {trick_id}.",
    "trainer.save_failed": (
        "No se pudo guardar el trainer en {path}. Comprueba la carpeta y los permisos."
    ),
    "workspace.save_failed": (
        "No se pudo guardar el workspace en {path}. Comprueba la carpeta y los permisos."
    ),
    "chat.message_required": "El mensaje no puede estar vacío.",
    "agent.empty_turn": "El proveedor no devolvió texto ni herramientas. Inténtalo de nuevo.",
    "agent.step_limit": (
        "El agente superó el límite de pasos consecutivos. "
        "Reformula la petición y continúa desde el estado actual."
    ),
    "tool.fix_cause": "Corrige la causa indicada y vuelve a intentar la operación.",
    "tool.invalid_operation": "La operación solicitada no es válida.",
    "tool.review_state": "Revisa los datos y el estado actual antes de volver a intentarlo.",
    "tool.safe_failure": "M@D-Engine no pudo completar la herramienta de forma segura.",
    "tool.safe_hint": "Revisa el estado de la aplicación y vuelve a intentarlo.",
    "tool.response_large": "La respuesta supera el límite seguro de tamaño.",
    "tool.response_filter": "Usa un filtro más específico o solicita una página más pequeña.",
    "tool.description.list_processes": (
        "Lista procesos locales autorizados; úsala antes de proponer cuál seleccionar."
    ),
    "tool.description.attach_process": (
        "Adjunta M@D-Engine a un PID; úsala solo tras la selección explícita del usuario."
    ),
    "tool.description.detach_process": (
        "Desacopla el proceso actual; úsala cuando el usuario quiera terminar la sesión."
    ),
    "tool.description.get_attached_process": (
        "Consulta el proceso vinculado; úsala para confirmar identidad y arquitectura."
    ),
    "tool.description.start_scan": (
        "Inicia un primer escaneo tipado; úsala después de conocer el valor inicial."
    ),
    "tool.description.refine_scan": (
        "Refina los candidatos actuales; úsala después de que el usuario provoque un cambio."
    ),
    "tool.description.cancel_scan": (
        "Cancela el escaneo en curso; úsala cuando el usuario lo solicite."
    ),
    "tool.description.get_scan_status": (
        "Consulta estado y candidatos; úsala antes de decidir el siguiente paso."
    ),
    "tool.description.list_scan_results": (
        "Devuelve una página acotada de candidatos; úsala para inspeccionar pocos resultados."
    ),
    "tool.description.read_address": (
        "Lee una dirección conocida con un tipo concreto; nunca inventes la dirección."
    ),
    "tool.description.add_watch": (
        "Añade una dirección candidata a vigilancia; úsala cuando queden pocos candidatos."
    ),
    "tool.description.list_watches": (
        "Lista las vigilancias actuales; úsala antes de escribir, congelar o eliminar."
    ),
    "tool.description.list_trainer_tricks": (
        "Lista los trucos guardados para el proceso adjunto y su estado actual."
    ),
    "tool.description.save_trainer_trick": (
        "Guarda como trainer una vigilancia ya probada. Llámala únicamente después "
        "de que el usuario diga que el truco funciona; siempre exige confirmación."
    ),
    "tool.description.write_watch": (
        "Escribe un valor en una vigilancia existente; requiere autorización de escritura."
    ),
    "tool.description.freeze_watch": (
        "Congela una vigilancia en un valor; requiere autorización y tiene escritura periódica."
    ),
    "tool.description.unfreeze_watch": (
        "Descongela una vigilancia; úsala para detener sus escrituras periódicas."
    ),
    "tool.description.remove_watch": (
        "Elimina una vigilancia; úsala solo para una entrada identificada por su id."
    ),
    "tool.description.save_workspace": (
        "Guarda la sesión en la carpeta segura de workspaces usando solo un nombre."
    ),
    "tool.description.load_workspace": (
        "Carga una sesión desde la carpeta segura de workspaces usando solo un nombre."
    ),
    "tool.unknown": "La herramienta solicitada no existe.",
    "tool.use_published": "Usa una de las herramientas publicadas por M@D-Engine.",
    "tool.invalid_arguments": "Los argumentos no tienen el formato requerido.",
    "tool.fix_schema": (
        "Corrige los campos indicados por el esquema estricto y vuelve a intentarlo."
    ),
    "provider.script_exhausted": (
        "El proveedor de prueba agotó los turnos programados. Añade otro ProviderTurn al guion."
    ),
    "scan.stats.candidates": "Candidatos",
    "scan.stats.regions": "Regiones analizadas",
    "scan.stats.bytes": "Bytes analizados",
    "scan.stats.duration": "Duración del último escaneo",
    "scan.stats.refinements": "Refinamientos",
    "scan.stats.type": "Tipo",
    "scan.stats.last_condition": "Última condición",
    "error.no_scan_ready": (
        "No hay un escaneo listo para refinar. Ejecuta primero un escaneo inicial."
    ),
    "watch.freeze_value_required": "Indica un valor deseado antes de congelar la vigilancia.",
    "trainer.current_value_mismatch": (
        "El valor actual ya no coincide con el valor activado. "
        "Prueba de nuevo el truco antes de guardarlo."
    ),
    "trainer.deactivate_before_edit": "Desactiva el truco antes de editar sus valores.",
    "trainer.disabled_value_missing": "El truco no tiene un valor para desactivarlo.",
    "workspace.wrong_process": (
        "El workspace pertenece a {workspace_process}; el proceso adjunto es {attached_process}."
    ),
    "workspace.architecture_mismatch": (
        "La arquitectura del workspace no coincide con el proceso adjunto."
    ),
    "error.agent_identity_mismatch": (
        "El proceso adjunto no coincide con la identidad autorizada para el agente. "
        "Pide al usuario que vuelva a seleccionarlo."
    ),
    "schema.unsupported": "El esquema usa palabras clave no admitidas: {keywords}",
    "tool.watch_missing": (
        "La vigilancia indicada no existe. Actualiza la lista y elige un id válido."
    ),
    "tool.workspace_name_required": "El nombre del workspace no puede estar vacío.",
    "tool.workspace_name_alnum": "El nombre del workspace debe contener letras o números.",
    "tool.workspace_confined": ("El workspace debe permanecer en la carpeta segura de M@D-Engine."),
    "tool.timeout_range": "El tiempo de espera debe estar entre 1 y 120000 ms.",
    "tool.no_initial_scan_type": "No hay un escaneo inicial cuyo tipo se pueda refinar.",
    "tool.no_attached_process": "No hay ningún proceso adjunto.",
    "watch.write_ok": "Valor escrito en la vigilancia.",
    "tool.workspace_name_only": "Indica solo un nombre de workspace, no una ruta.",
    "tool.process_detached": "Proceso desacoplado.",
    "tool.scan_cancel_requested": "Cancelación solicitada.",
    "tool.watch_frozen": "Vigilancia congelada.",
    "tool.watch_unfrozen": "Vigilancia descongelada.",
    "tool.watch_removed": "Vigilancia eliminada.",
    "tool.workspace_saved": "Workspace guardado.",
    "tool.workspace_loaded": "Workspace cargado.",
    "tool.agent_detach_reason": "Desacoplado por el agente con autorización del usuario.",
    "error.logo_load": "No se pudo cargar el logo de Mad Mod Engine.",
    "worker.timeout_positive": "El tiempo de espera de herramientas debe ser positivo.",
    "worker.parentless_required": (
        "Un worker debe crearse sin padre antes de moverlo a un QThread."
    ),
    "error.qt_application_incompatible": "Ya existe una aplicación Qt incompatible.",
    "scan.vector_shape_mismatch": "Los vectores actual y anterior deben tener la misma forma.",
    "scan.previous_required": "Este modo necesita un escaneo anterior para poder comparar.",
    "scan.unknown_initial_only": (
        "Valor desconocido inicial solo puede usarse en el primer escaneo."
    ),
    "scan.previous_type_mismatch": ("El tipo de dato debe coincidir con el escaneo anterior."),
    "watch.duplicate": "Ya existe una vigilancia con id {watch_id}.",
    "watch.missing": "No existe la vigilancia {watch_id}.",
    "workspace.duplicate_watches": (
        "El workspace contiene identificadores de vigilancia duplicados."
    ),
    "workspace.watch_model_expected": "Se esperaba un modelo de vigilancia de workspace.",
    "workspace.pointer_chain_missing": (
        "La vigilancia {label} referencia una cadena de punteros ausente."
    ),
    "watch.frozen_value_missing": "La vigilancia congelada no tiene un valor deseado.",
    "process.open_access_denied": (
        "Acceso denegado al PID {pid}. Ejecuta M@D-Engine como administrador "
        "o elige un proceso de tu mismo nivel de integridad."
    ),
    "process.open_failed": (
        "No se pudo abrir el PID {pid}. Actualiza la lista y vuelve a intentarlo."
    ),
    "process.note.protected": "proceso protegido",
    "process.note.unavailable": "acceso no disponible",
    "process.note.path_inaccessible": "ruta no accesible",
    "process.note.finished": "proceso finalizado",
    "workspace.filter": "Workspace de M@D-Engine (*.json)",
    "watch.column.name": "Nombre",
    "watch.column.address": "Dirección",
    "watch.column.type": "Tipo",
    "watch.column.value": "Valor",
    "watch.column.desired": "Deseado",
    "architecture.unknown": "Desconocida",
    "error.qt_instance": "Existe una instancia Qt que no es QApplication.",
    "agent.provider_busy": (
        "Espera a que termine la respuesta actual antes de cambiar el proveedor."
    ),
    "settings.agent_busy": (
        "Espera a que termine la respuesta actual antes de cambiar los ajustes."
    ),
    "results.unknown_order_column": "Columna de orden desconocida: {column}",
    "watch.partial_write_detail": (
        "Escritura parcial: {written} de {expected} bytes en {address}."
    ),
    "region.private": "Privada",
    "region.image": "Imagen",
    "region.mapped": "Mapeada",
    "region.unknown": "Desconocida",
    "watch.column.frozen": "Congelado",
    "watch.column.interval": "Intervalo",
    "watch.column.notes": "Notas",
    "watch.type.int8": "Int8",
    "watch.type.int16": "Int16",
    "watch.type.int32": "Int32",
    "watch.type.int64": "Int64",
    "watch.type.uint8": "UInt8",
    "watch.type.uint16": "UInt16",
    "watch.type.uint32": "UInt32",
    "watch.type.uint64": "UInt64",
    "watch.type.float32": "Float32",
    "watch.type.float64": "Float64",
    "watch.type.bool": "Booleano",
    "watch.type.string_utf8": "Texto UTF-8",
    "watch.type.string_utf16": "Texto UTF-16 LE",
    "watch.type.aob": "Patrón AOB",
    "watch.type.bytes": "Bytes",
    "watch.tooltip.error": "Último error: {error}",
    "watch.interval_value": "{value} ms",
    "watch.interval_suffix": " ms",
    "watch.address.chain": "{module}+0x{offset:X} · {count} desplazamientos",
    "watch.address.module": "{module}+0x{offset:X}",
    "watch.address.unresolved": "Sin resolver",
    "watch.address_dialog.title": "Añadir dirección a vigilancia",
    "watch.address_dialog.default_name": "Nueva vigilancia",
    "watch.address_dialog.address_placeholder": "0x00007FF600001000",
    "watch.label.name": "Nombre",
    "watch.label.address": "Dirección hexadecimal",
    "watch.label.type": "Tipo",
    "watch.label.interval": "Intervalo",
    "watch.label.notes": "Notas",
    "watch.action.add_address": "Añadir dirección…",
    "watch.action.add_pointer": "Añadir cadena de punteros…",
    "watch.action.remove": "Eliminar",
    "watch.action.freeze_all": "Congelar todo",
    "watch.action.unfreeze_all": "Descongelar todo",
    "watch.action.save_workspace": "Guardar workspace…",
    "watch.action.load_workspace": "Cargar workspace…",
    "watch.action.create_trainer": "Crear trainer manual…",
    "watch.action.confirm_add": "Añadir",
    "watch.action.cancel": "Cancelar",
    "watch.action.close": "Cerrar",
    "watch.accessible.table": "Tabla de vigilancia de memoria",
    "watch.accessible.add_address": "Añadir una dirección absoluta a vigilancia",
    "watch.accessible.add_pointer": "Añadir una cadena de punteros a vigilancia",
    "watch.accessible.remove": "Eliminar las vigilancias seleccionadas",
    "watch.accessible.freeze_all": "Congelar todas las vigilancias con valor deseado",
    "watch.accessible.unfreeze_all": "Descongelar todas las vigilancias",
    "watch.accessible.save_workspace": "Guardar el workspace actual",
    "watch.accessible.load_workspace": "Cargar un workspace",
    "watch.accessible.create_trainer": "Crear un trainer manual con la vigilancia seleccionada",
    "watch.accessible.address_name": "Nombre de la nueva vigilancia",
    "watch.accessible.absolute_address": "Dirección absoluta hexadecimal",
    "watch.accessible.address_type": "Tipo de dato de la nueva vigilancia",
    "watch.accessible.address_interval": "Intervalo de refresco de la nueva vigilancia",
    "watch.accessible.address_notes": "Notas de la nueva vigilancia",
    "watch.accessible.address_error": "Error de validación de la dirección",
    "watch.accessible.confirm_add": "Confirmar nueva vigilancia",
    "watch.accessible.cancel_add": "Cancelar nueva vigilancia",
    "watch.error.title": "No se pudo actualizar la vigilancia",
    "watch.error.name_required": "Escribe un nombre para la vigilancia.",
    "watch.error.address_required": "Escribe una dirección hexadecimal.",
    "watch.error.invalid_address": "La dirección hexadecimal no es válida.",
    "watch.error.type_required": "Selecciona un tipo de dato.",
    "watch.warning.title": "No se congelaron todas las vigilancias",
    "watch.warning.freeze_missing": (
        "{count} vigilancias no tienen un valor actual ni deseado. "
        "Escribe un valor antes de congelarlas."
    ),
    "watch.workspace.save_title": "Guardar workspace",
    "watch.workspace.load_title": "Cargar workspace",
    "watch.workspace.filter": "Workspace de M@D-Engine (*.json)",
    "trainer.manual.title": "Crear trainer manual",
    "trainer.manual.name": "Nombre del truco",
    "trainer.manual.type": "Tipo de dato",
    "trainer.manual.mode": "Comportamiento",
    "trainer.manual.enabled": "Valor al activar",
    "trainer.manual.disabled": "Valor al desactivar",
    "trainer.manual.interval": "Intervalo",
    "trainer.manual.notes": "Notas",
    "trainer.manual.save": "Probar y guardar",
    "trainer.manual.cancel": "Cancelar",
    "trainer.manual.confirm": "Probar y guardar el trainer manual «{name}»",
    "trainer.manual.saved": "Trainer manual «{name}» guardado y activado.",
    "trainer.manual.name_required": "Escribe un nombre para el truco.",
    "trainer.manual.enabled_required": "Escribe el valor que se aplicará al activar.",
    "trainer.manual.disabled_required": (
        "La escritura reversible necesita un valor para desactivar."
    ),
    "trainer.manual.invalid_value": "El valor no es válido para el tipo {type}.",
    "trainer.manual.unfreeze_first": (
        "Descongela la vigilancia antes de convertirla en un trainer."
    ),
    "pointer.title": "Cadena de punteros",
    "pointer.default_name": "Nueva cadena",
    "pointer.label.name": "Nombre",
    "pointer.label.module": "Módulo",
    "pointer.label.base_offset": "Offset base hexadecimal",
    "pointer.label.type": "Tipo final",
    "pointer.group.offsets": "Desplazamientos",
    "pointer.group.resolution": "Resolución paso a paso",
    "pointer.offset.placeholder": "0x10 o -0x8",
    "pointer.action.add_offset": "Añadir desplazamiento",
    "pointer.action.remove_offset": "Eliminar desplazamiento",
    "pointer.action.resolve": "Resolver",
    "pointer.action.save": "Guardar en workspace",
    "pointer.action.cancel": "Cancelar",
    "pointer.column.index": "Índice",
    "pointer.column.address": "Dirección",
    "pointer.column.value": "Valor leído",
    "pointer.column.ok": "Estado",
    "pointer.final.pending": "Dirección final: pendiente de resolución",
    "pointer.final.unresolved": "Dirección final: no resuelta",
    "pointer.final.address": "Dirección final: {address}",
    "pointer.final_value.pending": "Valor final: pendiente de resolución",
    "pointer.final_value.unavailable": "Valor final: no disponible",
    "pointer.final.value": "Valor final: {value}",
    "pointer.status.ready": "Edita la cadena y pulsa Resolver.",
    "pointer.status.resolve_failed": "No se pudo resolver la cadena.",
    "pointer.status.value_failed": (
        "La dirección se resolvió, pero no se pudo leer el valor: {error}"
    ),
    "pointer.status.resolved": "Cadena resuelta. Ya puedes guardarla en el workspace.",
    "pointer.value.unavailable": "No disponible",
    "pointer.value.yes": "Correcto",
    "pointer.value.no": "Error",
    "pointer.module.item": "{name} · base {base}",
    "pointer.error.invalid_offset": "El desplazamiento «{value}» no es hexadecimal.",
    "pointer.error.modules": "No se pudieron cargar los módulos: {error}",
    "pointer.error.no_modules": "El proceso no expone módulos utilizables.",
    "pointer.error.name_required": "Escribe un nombre para la cadena.",
    "pointer.error.module_required": "Selecciona un módulo.",
    "pointer.error.invalid_base_offset": "El offset base hexadecimal no es válido.",
    "pointer.error.offset_required": "Añade al menos un desplazamiento.",
    "pointer.error.type_required": "Selecciona el tipo del valor final.",
    "pointer.error.resolve_before_save": (
        "Resuelve de nuevo la cadena después de cualquier cambio antes de guardarla."
    ),
    "pointer.accessible.name": "Nombre de la cadena de punteros",
    "pointer.accessible.module": "Módulo base de la cadena de punteros",
    "pointer.accessible.base_offset": "Offset base hexadecimal",
    "pointer.accessible.type": "Tipo del valor final",
    "pointer.accessible.offsets": "Lista editable de desplazamientos",
    "pointer.accessible.new_offset": "Nuevo desplazamiento hexadecimal",
    "pointer.accessible.add_offset": "Añadir el desplazamiento",
    "pointer.accessible.remove_offset": "Eliminar desplazamientos seleccionados",
    "pointer.accessible.steps": "Pasos de resolución de la cadena",
    "pointer.accessible.final_address": "Dirección final resuelta",
    "pointer.accessible.final_value": "Valor de la dirección final",
    "pointer.accessible.status": "Estado de la resolución",
    "pointer.accessible.resolve": "Resolver la cadena de punteros",
    "pointer.accessible.save": "Guardar la cadena como vigilancia en el workspace",
    "pointer.accessible.cancel": "Cerrar sin guardar la cadena",
    "status.detached_by_user": "Desacoplado por el usuario.",
    "status.attached_ok": "Adjunto a {name} (PID {pid}).",
    "status.scan_reset": "Sesión reiniciada. El proceso sigue adjunto.",
    "results.reinterpreted": "{address} como {type}: {value}",
    "help.title": "Ayuda de M@D-Engine",
    "help.body": (
        "Selecciona un proceso autorizado, elige tipo y condición, y usa F5 para el primer "
        "escaneo. Cambia el valor en el proceso y usa F6 para refinar. Ctrl+W añade el "
        "resultado seleccionado a vigilancia. Esc cancela un escaneo activo. Con el proceso "
        "adjunto en primer plano, Pause o Ctrl+Shift+º abre el overlay de chat y ajustes."
    ),
    "lab.attach_question": ("¿Adjuntarse a Memory Lab (PID {pid}) con permiso de escritura?"),
    "lab.launch_failed": "No se pudo iniciar Memory Lab.",
    "cli.description": "Inspección autorizada de memoria de procesos locales.",
    "cli.no_ai": "Inicia con el asistente de IA desactivado.",
    "cli.memory_lab": "Inicia el proceso de laboratorio.",
    "cli.log_level": "Nivel de detalle del registro.",
    "process.available": "Disponible",
    "process.unavailable": "No disponible",
}


class Language(StrEnum):
    """Supported persistent interface languages."""

    SPANISH = "es"
    ENGLISH = "en"


SPANISH_STRINGS = STRINGS
CATALOGS: dict[Language, dict[str, str]] = {
    Language.SPANISH: SPANISH_STRINGS,
    Language.ENGLISH: ENGLISH_STRINGS,
}
if ENGLISH_STRINGS.keys() != SPANISH_STRINGS.keys():
    missing = SPANISH_STRINGS.keys() - ENGLISH_STRINGS.keys()
    extra = ENGLISH_STRINGS.keys() - SPANISH_STRINGS.keys()
    raise RuntimeError(
        f"English catalog mismatch: missing={sorted(missing)}, extra={sorted(extra)}"
    )

_language = Language.SPANISH


def set_language(language: Language | str) -> None:
    """Select the process-wide interface catalog for subsequently created widgets."""
    global _language
    _language = Language(language)


def get_language() -> Language:
    """Return the currently selected interface language."""
    return _language


def t(key: str, **kw: object) -> str:
    """Translate a key in the active catalog and interpolate named values."""
    return CATALOGS[_language][key].format(**kw)


def architecture_label(value: str) -> str:
    """Return a localized architecture name while preserving x86/x64 identifiers."""
    return t("architecture.unknown") if value == "desconocida" else value
