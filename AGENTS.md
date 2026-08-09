# Convenciones de M@D-Engine

## Arquitectura

- Toda operación de GUI y agente pasa por `AppController`; no se accede al backend desde herramientas del agente.
- La interfaz visible está en español y centralizada en `mempilot.i18n`; código, identificadores, docstrings y comentarios están en inglés.
- El acceso real a memoria se limita a `Win32MemoryBackend`; no se implementan evasión, inyección, drivers ni acceso remoto.
- No se permiten marcadores `TODO`, implementaciones vacías ni compatibilidad obsoleta.

## Verificación obligatoria

```powershell
ruff format --check .
ruff check .
mypy src
pytest -v
```

Los cambios de Win32 requieren además la prueba de integración marcada `windows and integration`. El empaquetado se valida con `scripts/build.ps1`.
