# Progreso de M@D-Engine

| Ola | Estado | Evidencia |
|---|---|---|
| 0 — Esqueleto | Completada | Ruff, mypy y 19 pruebas verdes |
| 1 — Núcleo y laboratorio | Completada | Ruff, mypy y 81 pruebas verdes |
| 2 — Fachada e interfaz | Completada | Ruff, mypy, 91 pruebas y smoke offscreen verdes |
| 3 — Agente de IA | Completada | Ruff, mypy, 120 pruebas y smoke sin IA verdes |
| 4 — Pruebas cruzadas | Completada | Ruff, mypy, 164 pruebas y roundtrip Win32 verdes |
| 5 — Entrega | Completada | 190 pruebas, trainers manuales y paquete PyInstaller verificados |

## Verificación final

- `ruff format --check .`: 110 archivos formateados.
- `ruff check .`: todas las comprobaciones superadas.
- `mypy src`: sin problemas en 63 archivos fuente.
- `pytest -v`: 190 pruebas superadas, incluida la integración Win32 real.
- `scripts/build.ps1`: ejecutable generado en `dist\M@D-Engine\M@D-Engine.exe`.
- Smoke empaquetado final: splash con el logo, título `M@D-Engine` y ventana principal operativos;
  PyInstaller incrustó `assets\mad-mod-engine.ico` en el ejecutable.
- Smoke empaquetado final: el control **Crear trainer manual…** está presente sin proveedor de IA;
  la edición de valores activado/desactivado y su siguiente activación se verificaron en GUI.
- Prueba real de conversación prolongada: 43.029 caracteres de historial se compactaron y
  Antigravity respondió `CONTEXTO_OK` sin superar el límite de comandos de Windows.
- Cierre del smoke: ningún proceso `M@D-Engine` quedó activo.
- SHA-256 de `M@D-Engine.exe`:
  `a877f8298a7111be0105c5f97508942e8a7954c3de55661e5ce781f68cce5f2a`.
