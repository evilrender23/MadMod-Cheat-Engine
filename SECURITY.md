# Seguridad de M@D-Engine

## Modelo de permisos

Cada adjunto abre uno de dos handles mínimos:

- **Sólo lectura:** consulta del proceso y `PROCESS_VM_READ`; habilita regiones, módulos, escaneos, refinamientos, lectura, vigilancia y resolución de punteros.
- **Lectura-escritura:** añade `PROCESS_VM_WRITE | PROCESS_VM_OPERATION`; habilita escritura y congelado además de lo anterior.

El usuario selecciona proceso y nivel. `AppController` valida en cada operación que el handle siga abierto, el proceso siga vivo y, para el agente, que PID, hora de creación, ruta y arquitectura coincidan con la identidad autorizada. M@D-Engine no se autoeleva y nunca amplía un handle sin una nueva selección explícita.

## Autenticación de las CLIs

M@D-Engine no solicita, lee ni persiste claves de API. Inicia `agy`, `codex` o `claude` como proceso
hijo y reutiliza la sesión que el usuario abrió directamente en esa herramienta. El adaptador
elimina variables de claves de API conocidas del entorno hijo, nunca invoca mediante shell y no
registra prompts, stdout ni stderr. Cada turno usa un directorio temporal vacío y salida JSON
validada; las herramientas internas se deshabilitan cuando la CLI lo permite y Antigravity se
ejecuta en modo plan/sandbox sin autoaprobación. Una CLI ausente, no autenticada o incompatible
falla de forma cerrada; la inspección manual permanece disponible.

## Confirmaciones

En modo guiado, escribir, congelar y cargar operaciones mutables propuestas por IA devuelven una solicitud de confirmación con proceso, dirección, tipo y valor. Sólo `Confirmar` autoriza la ejecución; `Rechazar`, cerrar la tarjeta o agotar el tiempo la deniega. Una confirmación no puede reutilizarse para otra llamada ni para otro proceso.

### Guardado y activación de trainers

`save_trainer_trick` exige confirmación expresa incluso en modo autónomo. Antes de persistir,
`AppController` vuelve a leer la dirección mediante el backend y rechaza el guardado si el valor
ya no coincide con el que el usuario probó. El catálogo se limita al nombre y arquitectura del
proceso, dirección portable, tipo, valores de activación y desactivación y notas; excluye PID,
handles, lecturas actuales, estado congelado y credenciales.

Los trainers se cargan inactivos en cada nuevo adjunto. También pueden crearse sin IA desde una
vigilancia: si el valor elegido difiere del actual, la GUI muestra una confirmación exacta antes de
probarlo y guardarlo. Los valores de un trainer guardado sólo se pueden editar desde el overlay
mientras esté inactivo. Activar o desactivar vuelve a pasar por `AppController`, el handle actual,
la identidad adjunta, la política y la auditoría. El overlay deshabilita esas acciones en sólo
lectura y confirma cualquier activación o restauración que escriba memoria. Un trainer de
congelado se desactiva descongelando; uno de escritura restaura obligatoriamente el valor
desactivado guardado.

## Modo autónomo

La activación muestra literalmente los permisos concedidos y exige consentimiento. La autorización queda vinculada a una única identidad de proceso, conserva el nivel de acceso existente, permite escribir y congelar sólo mediante herramientas registradas y aplica un máximo visible de escrituras. El agente no puede cambiar de proceso, aumentar el cupo, ampliar permisos, cargar un workspace sin respetar la política ni continuar tras cancelación. Desactivar el modo o desacoplar revoca la concesión.

## Overlay ligado al proceso

Los atajos globales sólo abren el overlay cuando la ventana en primer plano pertenece al PID de
la identidad adjunta; el overlay conserva además PID, hora de creación, ruta y arquitectura para
detectar una sustitución del proceso. Cambiar de proceso, desacoplar o perderlo oculta el overlay.
La escritura manual y el congelado siguen requiriendo el handle de lectura-escritura, una
vigilancia resuelta por `AppController` y confirmación explícita. El overlay no inyecta código,
no se dibuja dentro del proceso objetivo y no amplía permisos.

## Procesos protegidos

`NEVER_ATTACH` bloquea siempre procesos críticos como System, Registry, Session Manager, CSRSS, wininit y servicios esenciales; también se bloquean PID 0 y 4 y el propio proceso de M@D-Engine. `HIDDEN_BY_DEFAULT` añade procesos del sistema y de escritorio que no son objetivos normales. Mostrar procesos del sistema sólo elimina el filtro visual: nunca elimina `NEVER_ATTACH` ni las comprobaciones de integridad.

## Técnicas fuera de alcance

M@D-Engine no contiene ni acepta bypass de anti-cheat, evasión, ocultación, inyección de DLL, ejecución dentro del objetivo, drivers de kernel, depuración ofensiva, modificación remota ni técnicas para eludir controles de acceso. Un error de acceso se presenta al usuario; no se intenta sortearlo.

## Reporte de problemas

No publique credenciales, dumps, direcciones vinculadas a datos sensibles ni logs sin revisar. Incluya versión de Windows, arquitectura, versión de M@D-Engine, pasos mínimos, modo de acceso y el mensaje redactado. Para una vulnerabilidad, contacte privadamente al mantenedor del repositorio antes de abrir un informe público; para errores funcionales puede abrir una incidencia sin secretos ni datos de terceros.
