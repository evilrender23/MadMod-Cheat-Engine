"""Domain exceptions with safe, actionable user messages."""


class MemPilotError(Exception):
    """Base class for expected application errors."""

    default_message = "La operación no pudo completarse. Revisa los datos e inténtalo de nuevo."

    def user_message(self) -> str:
        """Return an actionable Spanish message safe for display."""
        return str(self) or self.default_message


class ProcessNotFoundError(MemPilotError):
    default_message = "El proceso ya no existe. Actualiza la lista y selecciona otro proceso."


class ProcessNotAllowedError(MemPilotError):
    default_message = "Ese proceso está protegido. Selecciona un proceso de usuario autorizado."


class AccessDeniedError(MemPilotError):
    default_message = (
        "Acceso denegado. Usa un proceso de tu nivel de integridad o ejecuta como administrador."
    )


class ProcessExitedError(MemPilotError):
    default_message = "El proceso terminó. Vuelve a seleccionarlo si lo inicias de nuevo."


class NotAttachedError(MemPilotError):
    default_message = "No hay ningún proceso adjunto. Selecciona un proceso antes de continuar."


class WriteNotPermittedError(MemPilotError):
    default_message = "La sesión es de solo lectura. Vuelve a adjuntarte con permiso de escritura."


class MemoryReadError(MemPilotError):
    default_message = (
        "No se pudo leer la memoria. Comprueba que el proceso siga activo "
        "y la dirección sea válida."
    )


class MemoryWriteError(MemPilotError):
    default_message = (
        "No se pudo escribir la memoria. Comprueba el permiso y la protección de la región."
    )


class InvalidAddressError(MemPilotError):
    default_message = (
        "La dirección no pertenece a una región válida. "
        "Actualiza los resultados e inténtalo de nuevo."
    )


class ValueParseError(MemPilotError):
    default_message = "El valor no tiene el formato esperado para el tipo seleccionado."


class PatternError(MemPilotError):
    default_message = "El patrón AOB no es válido. Usa bytes hexadecimales y ?? para comodines."


class ScanError(MemPilotError):
    default_message = (
        "El escaneo no pudo completarse. Reduce el rango o usa un valor más específico."
    )


class ScanCancelled(MemPilotError):  # noqa: N818 - public contract
    default_message = "El escaneo fue cancelado. Puedes iniciar uno nuevo."


class WorkspaceError(MemPilotError):
    default_message = "El workspace no es válido. Comprueba el archivo o crea uno nuevo."


class PolicyDenied(MemPilotError):  # noqa: N818 - public contract
    default_message = (
        "La política de seguridad impide esta operación. Revisa el modo y los permisos del agente."
    )


class ProviderError(MemPilotError):
    default_message = (
        "El proveedor de IA no respondió correctamente. Revisa la conexión y la configuración."
    )
