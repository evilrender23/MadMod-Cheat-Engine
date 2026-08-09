# Plan de M@D-Engine

## Arquitectura

M@D-Engine separa presentación, fachada, dominio y acceso Win32. `AppController` es la única fachada compartida por la GUI y el agente. El escáner usa un trabajador único y núcleos NumPy; la vigilancia y el congelado comparten un planificador. El agente sólo ejecuta herramientas Pydantic tipadas y aplica una política ligada a la identidad del proceso.

## Hitos

1. Esqueleto, contratos y configuración.
2. Backend Win32, escáner, servicios y Memory Lab.
3. Fachada, hilos, vigilancia e interfaz Qt.
4. Agente de IA con confirmaciones y límites.
5. Pruebas cruzadas, empaquetado y documentación.

## Riesgos

- Reutilización de PID: se compara PID y hora de creación y se conserva el handle original.
- Lecturas parciales: el escáner acepta copias parciales y descarta zonas ilegibles.
- Volumen de candidatos: paginación NumPy y límite explícito, sin truncado silencioso.
- Escrituras del agente: confirmación guiada o límite autónomo ligado al proceso.
- Empaquetado Qt/CLIs externas: `--onedir`, detección por `PATH`, backend Windows explícito y prueba del binario.

## Estrategia de pruebas

Núcleos puros contra un backend en memoria; integración real contra un proceso hijo; interfaz con Qt offscreen; recorrido de extremo a extremo de lectura, escaneo, refinamiento, escritura y congelado.

## Criterios de aceptación

Aplicación Windows x64 funcional, UI española, adjunto seguro, escaneos y refinamientos, vigilancia, escritura y congelado, punteros conocidos, workspaces, agente tipado y seguro, Memory Lab, modo sin IA, apagado limpio, puertas de calidad verdes y ejecutable PyInstaller probado.
