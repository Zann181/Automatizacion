# Plan de Ejecución para Agentes: Sistema de Detección PLC Configurable

Este documento describe el plan de implementación estructurado y escalable para completar el sistema de automatización PLC basado en categorías detectadas por cámara. Está diseñado para que cualquier subagente (por ejemplo, `cavecrew-builder` o el agente principal) pueda ejecutarlo paso a paso.

## Contexto
El sistema interactúa con un PLC a través de comandos y reacciona a los eventos de detección de una cámara.
- **Categoría "ACTIVE"**: Apaga el motor por un tiempo determinado y luego lo enciende.
- **Categorías Numéricas (1, 2, 3)**: Avanzan el motor por una duración específica o no hacen nada.
- **Objetivo**: Hacer que todos estos tiempos y parámetros sean configurables a través de una interfaz web, persistiendo en una base de datos SQLite.

---

## Fases de Ejecución

### Fase 1: Capa de Persistencia (Base de Datos)
**Objetivo**: Crear un repositorio para leer y actualizar la configuración de la cámara (`CameraSettings`) de forma síncrona.

- **Tarea 1.1**: Verificar que el modelo `CameraSettings` exista en `src/database/models.py`.
  - Campos esperados: `motor_off_duration`, `cat1_duration`, `cat2_duration`, `cat3_duration`, `auto_execute`.
- **Tarea 1.2**: Crear `src/infrastructure/camera/SettingsRepository.py`.
  - Implementar clase `SettingsRepository` que reciba una sesión de BD.
  - Método `get_settings()`: Obtiene la primera fila o crea una por defecto. Devuelve un diccionario con los valores tipados (floats, booleanos).
  - Método `update_settings(payload: dict)`: Actualiza la fila existente y devuelve el nuevo estado.

### Fase 2: Capa de Casos de Uso (Lógica de Negocio)
**Objetivo**: Modificar la lógica de negocio para utilizar la configuración persistida en lugar de valores estáticos.

- **Tarea 2.1**: Actualizar `src/application/camera/ExecutePlcUseCase.py`.
  - Importar `get_db` y `SettingsRepository`.
  - En el método `__call__`, obtener una sesión de base de datos (`with next(get_db()) as db:`).
  - Cargar los parámetros (`settings_data`) e instanciar el objeto de dominio `Settings`.
  - Asegurar que la lógica posterior (apagar motor, avanzar categorías) use los tiempos de `settings`.

### Fase 3: Capa de Red y API (Backend Flask)
**Objetivo**: Exponer las configuraciones al frontend a través de endpoints REST.

- **Tarea 3.1**: Actualizar `src/server/app.py`.
  - Importar dependencias: `get_db`, `SettingsRepository`, `DetectionResult`, `ExecutePlcUseCase`.
  - Crear endpoint `GET /camera/settings` que devuelva un JSON con la configuración actual.
  - Crear endpoint `POST /camera/settings` que reciba un JSON, actualice la configuración mediante el repositorio y devuelva el resultado.
  - Crear endpoint `POST /camera/detect` que reciba una categoría y confianza, invoque `ExecutePlcUseCase` y retorne la acción realizada.

### Fase 4: Capa de Presentación (Frontend UI)
**Objetivo**: Permitir al usuario visualizar y modificar los tiempos directamente desde la web.

- **Tarea 4.1**: Actualizar `src/frontend/index.html`.
  - Agregar un botón flotante de "Settings" (`#settingsBtn`).
  - Agregar un modal oculto (`#settingsModal`) con campos de entrada (`<input type="number">`) para:
    - Motor off duration.
    - Category 1, 2 y 3 durations.
    - Auto execute (checkbox).
  - Agregar botones "Save" y "Close" en el modal.
- **Tarea 4.2**: Actualizar `src/frontend/app.js`.
  - Obtener las referencias del DOM para los nuevos elementos.
  - Implementar función `loadSettings()`: Hace fetch a `GET /camera/settings` y llena los inputs del modal.
  - Implementar función `saveSettings()`: Construye un payload, hace POST a `/camera/settings`, cierra el modal y recarga la UI.
  - Ligar los event listeners a los botones correspondientes.

### Fase 5: Pruebas y Verificación (QA)
**Objetivo**: Garantizar que todas las capas operen en conjunto sin errores.

- **Prueba 5.1 (Backend)**: Ejecutar el servidor (`python -m src.server.app`). Hacer peticiones cURL a `/camera/settings` (GET y POST) y validar las respuestas JSON y los cambios en `plc_logs.db`.
- **Prueba 5.2 (Frontend)**: Abrir la interfaz web, cliquear "Settings", modificar valores, guardarlos, cerrar el modal y reabrirlo para confirmar la persistencia.
- **Prueba 5.3 (Flujo Completo)**: Simular una detección mediante `POST /camera/detect` con `{"category": "ACTIVE", "confidence": 0.95}` y revisar los logs para confirmar que el motor se detiene y reinicia usando el tiempo configurado en la UI.

---

## Directrices para Agentes

1. **Modularidad**: Seguir el patrón de arquitectura limpia existente. Las dependencias externas (Base de datos, PLC) entran a través de repositorios; la lógica principal reside en los Casos de Uso.
2. **Robustez Async/Sync**: Notar que la conexión al PLC usa `asyncio`, mientras que SQLite (`sqlalchemy`) se utiliza de forma sincrónica para evitar problemas de hilos. El repositorio debe encapsular la carga de datos sin bloquear el hilo principal.
3. **Reporte**: Después de ejecutar cada fase, el agente responsable debe actualizar una lista de chequeo (o artefacto `task.md`) y notificar el éxito o fracaso, adjuntando logs o diffs relevantes.
