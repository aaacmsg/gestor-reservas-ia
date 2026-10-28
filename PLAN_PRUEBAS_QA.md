# Plan de QA - Gestor de Reservas

## 1. Alcance y estado observado

El proyecto usa Django 5.2, Python, SQLite, plantillas HTML renderizadas por el servidor y JavaScript con FullCalendar. La API de reservas y el acceso a datos se implementan con vistas Django y el ORM. Por ello, la base recomendada es `django.test.TestCase` y `Client`; las pruebas de navegador pueden añadirse con Playwright.

La inspeccion del repositorio muestra:

- Se agregaron pruebas automatizadas para el endpoint de reservas en `reservas/tests.py`.
- El modelo `User` de Django es la unica fuente de datos de cuenta; no se observa perfil con datos adicionales ni flujo de reserva rapida.
- El calendario muestra reservas y bloqueos (`Availability`), pero no se observa un calculo o interfaz de dias disponibles/ocupados como HU.
- No se observan graficos ni calculo de prevision de demanda para administradores.
- Si se toman como historias adicionales las funcionalidades presentes, las candidatas son reservas recurrentes y bloqueos administrativos. Confirmar con el equipo que coincidan con las dos HU aprobadas por el profesor.

**Estado de ejecucion:** se agrego `requirements.txt` con Django 5.2.4, se instalo esa dependencia en el entorno y se ejecuto `python manage.py test reservas`: **10 pruebas aprobadas**. `python manage.py check` tambien paso sin incidencias. No hay suite de navegador ni validacion visual automatizada.

## 2. Criterios de aceptacion y escenarios Gherkin

Los siguientes criterios son una propuesta verificable. Los detalles marcados como decisiones pendientes (por ejemplo, que significa exactamente “datos guardados”) deben acordarse con el equipo y quedar reflejados en la HU antes de cerrar la prueba.

### HU-01 - Reserva rapida para usuario recurrente

**Criterios de aceptacion**

1. Un usuario autenticado con los datos requeridos guardados puede iniciar una reserva sin volver a introducirlos.
2. El sistema muestra el recurso y el horario seleccionado antes de confirmar.
3. La reserva solo se crea si el horario sigue disponible en el servidor al momento de confirmar.
4. Si la sesion expiro, la entrada guardada no existe o el horario dejo de estar disponible, la operacion no crea una reserva y se informa el motivo.
5. La confirmacion se refleja en calendario y queda asociada al usuario autenticado.

```gherkin
Caracteristica: Reserva rapida de un usuario recurrente

  Escenario: Reservar con datos previamente guardados
    Dado que inicio sesion como usuario recurrente
    Y mi cuenta tiene guardados los datos requeridos para reservar
    Y el recurso y el horario seleccionado estan disponibles
    Cuando confirmo la reserva rapida
    Entonces el sistema crea una reserva asociada a mi cuenta
    Y no me solicita volver a introducir los datos guardados
    Y la reserva aparece en el calendario

  Escenario: Rechazar una reserva cuyo horario acaba de ocuparse
    Dado que inicio sesion como usuario recurrente
    Y el horario estaba disponible al abrir el flujo de reserva
    Cuando otro usuario reserva ese horario antes de mi confirmacion
    Y confirmo mi reserva
    Entonces el sistema informa que el horario ya no esta disponible
    Y no crea una reserva duplicada

  Escenario: Impedir reserva rapida sin sesion valida
    Dado que no tengo una sesion autenticada
    Cuando intento confirmar una reserva rapida
    Entonces el sistema solicita iniciar sesion
    Y no crea ninguna reserva
```

**Decision pendiente:** definir que informacion se guarda en la cuenta y si “rapida” significa autocompletar datos, reservar con una sola confirmacion u otro comportamiento. El codigo actual no modela un perfil adicional para esta informacion.

### HU-02 - Calendario dinamico de disponibilidad

**Criterios de aceptacion**

1. El calendario distingue visualmente dias/horarios disponibles, ocupados y bloqueados.
2. Una reserva o bloqueo nuevo se refleja al actualizar eventos, sin mostrar disponibilidad desactualizada.
3. Una franja ocupada o bloqueada no puede reservarse, aunque se intente enviar la solicitud directamente a la API.
4. Una franja libre del mismo dia sigue siendo seleccionable cuando otra franja de ese dia esta ocupada.
5. El estado se calcula para el recurso y periodo correctos; no se mezclan las reservas de otros recursos.

```gherkin
Caracteristica: Consulta dinamica de disponibilidad

  Escenario: Mostrar dias con horarios disponibles y ocupados
    Dado un recurso con horarios operativos definidos
    Y existen reservas y bloqueos para algunos horarios
    Cuando consulto el calendario del recurso
    Entonces los horarios ocupados y bloqueados se distinguen de los disponibles
    Y los horarios libres permanecen seleccionables

  Escenario: Actualizar disponibilidad despues de una reserva
    Dado que consulto un horario disponible
    Cuando una reserva valida se confirma para ese horario
    Y actualizo los eventos del calendario
    Entonces ese horario aparece ocupado
    Y deja de poder seleccionarse para una nueva reserva

  Escenario: Impedir una reserva en un bloqueo administrativo
    Dado que un administrador bloqueo una franja del recurso
    Cuando un usuario intenta reservar una franja que se cruza con el bloqueo
    Entonces el servidor rechaza la solicitud
    Y no se crea la reserva
```

**Decision pendiente:** aclarar si “dia disponible” significa que existe al menos una franja libre o que el dia completo esta libre; especificar horario operativo, zona horaria y regla para reservas en los limites de una franja.

### HU-03 - Graficos de prevision de demanda para administrador

**Criterios de aceptacion**

1. Solo usuarios con permiso administrativo pueden consultar la prevision.
2. El grafico presenta periodos, unidades y leyenda que permitan distinguir datos historicos de demanda prevista.
3. Los filtros de periodo/recurso actualizan los datos y la visualizacion de forma consistente.
4. La interfaz maneja correctamente ausencia de datos y errores, sin presentar una prevision ficticia como si fuera real.
5. Los valores del grafico corresponden a una agregacion reproducible de los datos de prueba y al metodo de prevision acordado.

```gherkin
Caracteristica: Prevision de demanda del administrador

  Escenario: Consultar la prevision con permiso administrativo
    Dado que inicio sesion con una cuenta administradora
    Y existen reservas historicas para el periodo seleccionado
    Cuando abro el panel de prevision y selecciono un recurso y un periodo
    Entonces se muestra un grafico con la demanda historica y la prevista
    Y los valores corresponden a los datos del periodo y recurso elegidos

  Escenario: Denegar el panel a un usuario sin permiso
    Dado que inicio sesion como usuario sin permisos administrativos
    Cuando intento abrir el panel de prevision
    Entonces el sistema deniega el acceso
    Y no expone los datos de administracion

  Escenario: Mostrar estado vacio sin historial suficiente
    Dado que no hay datos para el recurso y periodo seleccionados
    Cuando el administrador consulta la prevision
    Entonces el panel informa que no hay datos suficientes
    Y no presenta valores inventados como una prevision valida
```

**Decision pendiente:** acordar algoritmo, granularidad (por dia/semana), horizonte, tratamiento de cancelaciones y minimo de historial. Sin esta definicion no se puede validar la exactitud de la prevision.

## 3. Historias adicionales candidatas

Validar con el equipo que estas sean las dos HU adicionales elegidas; ambas se corresponden con funcionalidades descritas en el README y presentes parcialmente en el codigo.

### HU-04 - Reserva recurrente semanal

```gherkin
Caracteristica: Repetir una reserva semanalmente

  Escenario: Crear todas las repeticiones cuando los horarios estan libres
    Dado que inicio sesion
    Y el horario y sus siguientes dos repeticiones semanales estan disponibles
    Cuando creo la reserva con repeticion de dos semanas
    Entonces se crean tres reservas para el mismo recurso y horario semanal
    Y todas quedan asociadas a mi usuario

  Escenario: No dejar una serie parcialmente creada por un conflicto
    Dado que inicio sesion
    Y una de las repeticiones semanales ya esta ocupada
    Cuando solicito crear la serie
    Entonces el sistema informa el conflicto
    Y no deja reservas creadas parcialmente

  Escenario: Rechazar cantidad de repeticiones invalida
    Dado que inicio sesion
    Cuando envio una cantidad negativa, no numerica o fuera del limite acordado
    Entonces el sistema valida la entrada e informa el error
    Y no crea reservas
```

### HU-05 - Bloqueo administrativo de horarios

```gherkin
Caracteristica: Administrar bloqueos de un recurso

  Escenario: Administrador bloquea una franja libre
    Dado que inicio sesion como administrador
    Y la franja del recurso no tiene reservas
    Cuando guardo un bloqueo valido
    Entonces el bloqueo se guarda para ese recurso y horario
    Y el calendario lo muestra como no disponible

  Escenario: Usuario normal no puede administrar bloqueos
    Dado que inicio sesion como usuario sin permisos administrativos
    Cuando intento crear o modificar un bloqueo
    Entonces el sistema deniega la operacion
    Y no cambia la disponibilidad

  Escenario: Rechazar bloqueo con fechas invalidas o conflicto
    Dado que inicio sesion como administrador
    Cuando intento guardar un bloqueo con fin anterior al inicio
    O que se cruza con una reserva existente
    Entonces el sistema informa el error
    Y no guarda un bloqueo inconsistente
```

## 4. Estrategia de automatizacion y casos de integracion

### Capas recomendadas

| Capa | Herramienta/patron | Cobertura recomendada |
|---|---|---|
| Modelo y reglas | `django.test.TestCase` | Solapamientos, limites horarios, integridad de recursos/usuarios y validaciones. |
| Vistas/API | `django.test.Client` y `TestCase` | JSON, codigos HTTP, autenticacion, errores y efectos en la base de datos de prueba. |
| Interfaz web | Playwright (si se agrega como dependencia) | Flujo de login, calendario, seleccion de franja, errores visibles y refresco de eventos en navegador. |
| Regresion manual | Lista de ejecucion reproducible | Navegadores objetivo, permisos, zona horaria y estados vacios/con error. |

Usar la base de datos temporal que crea el runner; no ejecutar pruebas contra `db.sqlite3` con datos de uso. Para pruebas de navegador, sembrar datos de forma controlada y limpiar el entorno al terminar. No usar `crear_reservas_demo` como limpieza indiscriminada en una base compartida: el comando elimina todas las reservas existentes antes de crear datos demo.

### Casos clave front-end / back-end / base de datos

| ID | Tipo | Preparacion y accion | Resultado esperado |
|---|---|---|---|
| INT-01 | Positivo | Usuario autenticado envia POST JSON con recurso y horario libre. | HTTP 200; `success: true`; una fila `Booking` con usuario, recurso y fechas correctos; el GET de eventos la devuelve. |
| INT-02 | Negativo | Usuario anonimo envia POST para crear una reserva. | HTTP 403; cero filas nuevas; mensaje de autenticacion. |
| INT-03 | Negativo | Enviar una reserva que se solapa parcialmente con otra del mismo recurso. | Solicitud rechazada; cero filas nuevas. |
| INT-04 | Positivo | Enviar reservas del mismo horario para recursos diferentes. | Ambas se aceptan si no hay otra regla de negocio que lo impida. |
| INT-05 | Negativo | Enviar fechas faltantes, malformadas, fin <= inicio o recurso inexistente. | Error controlado con codigo HTTP apropiado; cero filas nuevas; sin excepcion HTML/500 sin manejar. |
| INT-06 | Negativo | Pedir reserva dentro de un bloqueo, sin depender de la validacion JavaScript. | Servidor rechaza la solicitud; cero filas nuevas. |
| INT-07 | Negativo | Crear una serie recurrente donde una semana intermedia este ocupada. | Ninguna reserva de la serie persiste si la regla acordada es atomica; respuesta identifica conflicto. |
| INT-08 | Positivo | GET de eventos para un recurso con reservas y bloqueos. | JSON con fechas ISO y eventos unicamente del recurso solicitado. |
| INT-09 | Negativo | Intentar administrar bloqueos/prevision como usuario sin permiso. | Acceso denegado en servidor; no hay cambios ni datos administrativos expuestos. |
| UI-01 | Navegador | Abrir calendario anonimamente y seleccionar una franja. | Se indica que debe autenticarse; no se crea reserva. |
| UI-02 | Navegador | Reservar una franja libre y refrescar eventos. | Confirmacion visible; evento actualizado sin recargar la pagina completa. |
| UI-03 | Navegador | Consultar recurso sin reservas/bloqueos o con error de carga. | Estado vacio/error claro; la pagina no se rompe ni muestra datos de otro recurso. |

Para no hacer tests fragiles, comprobar el contrato de la API y el estado de la base de datos, no el texto exacto de alertas salvo que ese texto sea requisito de aceptacion. El endpoint de creacion responde actualmente 200 al crear, 403 para usuarios anonimos, 400 para payloads o fechas invalidas, 404 para recursos inexistentes y 409 para conflictos; mantener estos codigos en el contrato de API.

## 5. Hallazgos y evidencia de IA

**No se encontro en el repositorio historial de prompts, respuestas de IA, diffs rechazados ni registros de ejecucion anteriores.** Por tanto, no es correcto atribuir los defectos siguientes a la IA sin contrastarlos con la evidencia del equipo. Sirven como hallazgos QA verificables y como candidatos para comparar con el historial de generacion.

| Ref. | Observacion basada en el codigo | Riesgo / prueba asociada | Evidencia necesaria para atribuirlo a IA |
|---|---|---|---|
| QA-F01 | La revision inicial encontro que el endpoint creaba ocurrencias en el mismo bucle donde detectaba conflictos. Se cambio para validar todas las ocurrencias antes de crear y envolver la escritura en una transaccion. | `test_recurring_bookings_are_all_or_nothing_on_conflict` confirma que el conflicto no deja una serie parcial. Suite actual: pasa. | Prompt/respuesta o commit que introdujo el comportamiento; esta evidencia no esta en el repositorio. |
| QA-F02 | La revision inicial encontro que los bloqueos se comprobaban en JavaScript, pero no en `api_crear_reserva`. El endpoint ahora rechaza cruces con `Availability`. | `test_blocked_time_is_rejected_by_api` confirma respuesta 409 y cero reservas nuevas. Suite actual: pasa. | Salida de IA/historial que permita atribuir el defecto; no disponible en el repositorio. |
| QA-F03 | La conversion permisiva de fechas/repeticiones se reemplazo con validacion de JSON, fechas, intervalo y entero no negativo. No se definio aun un maximo de semanas. | Casos para JSON/intervalo invalido pasan; falta acordar y probar el limite de recurrencia de negocio. | Prompt/diff rechazado y razon documentada; no disponible en el repositorio. |

Para cada ejemplo que se presente como “respuesta incorrecta de IA” o “cambio rechazado”, completar y adjuntar:

1. ID de evidencia y HU afectada.
2. Fecha, herramienta/modelo y prompt original (ocultar credenciales o datos personales).
3. Fragmento exacto generado y commit/diff relacionado.
4. Pasos para reproducir, entorno, datos sembrados y resultado esperado/obtenido.
5. Log, captura o salida de prueba que demuestre el fallo.
6. Decision del equipo (rechazado/corregido), cambio aplicado y prueba de regresion aprobada.

**Ejemplo de registro listo para completar (no constituye evidencia real):**

> ID: IA-___ | HU: ___ | Prompt: [adjuntar] | Respuesta/diff: [adjuntar] | Fallo observado: [pasos y salida] | Por que se rechazo: [impacto/requisito] | Correccion: [commit] | Regresion: [caso y resultado].  
> No completar con una respuesta inventada; si no existe el historial, registrar “evidencia no disponible” y capturar un caso real durante la siguiente iteracion.

## 6. Matriz de trazabilidad y evidencia para presentacion

| HU | Criterios / escenarios | Validacion automatizada propuesta | Evidencia a capturar | Estado observado |
|---|---|---|---|---|
| HU-01 Reserva rapida recurrente | AC 1-5; escenarios de exito, conflicto y sesion | Test de vista/API + prueba Playwright del flujo | Video/captura, request/response, fila de BD y resultado de regresion | Pendiente; no se observa flujo de reserva rapida ni datos de perfil |
| HU-02 Calendario dinamico | AC 1-5; disponibilidad, refresco, bloqueo | Tests de API y disponibilidad + Playwright | Calendario antes/despues, recurso y fechas, respuesta de API | Parcial; hay FullCalendar y eventos, falta disponibilidad diaria completa y validacion de bloqueo en servidor |
| HU-03 Prevision de demanda | AC 1-5; admin, filtros, sin datos | Tests de permisos/agregacion + Playwright | Usuario/rol, filtro, valores esperados vs grafico, captura | Pendiente; no se observa prevision ni grafico |
| HU-04 Reserva recurrente (candidata) | Serie completa, conflicto atomico, entradas invalidas | Tests de endpoint y BD | POST, JSON resultante y conteo de reservas | Parcial; 10 pruebas del endpoint pasan, incluyendo recurrencia positiva y atomica. Falta limite maximo acordado y pruebas concurrentes |
| HU-05 Bloqueos administrativos (candidata) | Crear, permisos, intervalos invalidos/conflictos | Tests de admin/API + Playwright | Registro de bloqueo y calendario actualizado; respuesta de permiso | Parcial; el endpoint ya verifica bloqueos y la prueba pasa. Falta completar permisos/reglas del admin y prueba de navegador |

**Criterio de salida para la demo:** cada criterio debe tener un caso ejecutable con resultado registrado; las evidencias deben corresponder al mismo build/commit presentado; los fallos abiertos deben tener severidad, responsable y decision documentada. No marcar como aprobadas las HU ausentes o las pruebas que no se hayan ejecutado.
