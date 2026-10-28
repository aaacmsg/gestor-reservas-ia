# Plan de QA - Gestor de Reservas

## 1. Alcance y estado observado

El proyecto usa Django 5.2, Python, SQLite, plantillas HTML renderizadas por el servidor y JavaScript con FullCalendar. La API de reservas y el acceso a datos se implementan con vistas Django y el ORM. Por ello, la base recomendada es `django.test.TestCase` y `Client`; las pruebas de navegador pueden añadirse con Playwright.

Se actualizo la rama `qa` con `origin/main` (commit `9ae2b0e`), que incorpora H1-H5: pagos guardados y reserva rapida, calendario dinamico, pronostico de demanda, mis reservas/cancelaciones y correo de confirmacion. Las historias adicionales se interpretan ahora como H4 Mis reservas y H5 Correo de confirmacion, conforme al codigo actualizado.

La suite automatizada de `reservas/tests.py` valida integraciones entre vistas, API, modelos, correo y base de datos. **Ultima ejecucion:** `python manage.py test reservas` con **29 pruebas aprobadas**; `python manage.py check` paso y `python manage.py makemigrations --check --dry-run` reporto que no hay migraciones pendientes. No se ha ejecutado E2E real en navegador; los componentes CDN (FullCalendar/Chart.js) requieren comprobacion manual o una suite browser aparte.

## 2. Criterios de aceptacion y escenarios Gherkin

Los criterios reflejan la funcionalidad observada en la version actual. Ajustar sus umbrales o reglas si la HU oficial del equipo define otros.

### HU-01 - Reserva rapida para usuario recurrente

**Criterios de aceptacion**

1. Un usuario autenticado que tiene un metodo de pago guardado puede seleccionarlo al reservar.
2. La reserva se crea con el usuario, horario, precio y ultimos cuatro digitos correctos; no se conserva numero completo, CVV ni vencimiento.
3. La reserva no se crea si no existe metodo guardado o si el horario ya no esta disponible.
4. El calendario se actualiza y se envia confirmacion cuando la cuenta tiene correo.

```gherkin
Caracteristica: Reserva rapida de un usuario recurrente

  Escenario: Reservar con datos previamente guardados
    Dado que inicio sesion como usuario recurrente
    Y mi cuenta tiene un metodo de pago guardado
    Y el recurso y el horario seleccionado estan disponibles
    Cuando confirmo la reserva rapida
    Entonces el sistema crea una reserva asociada a mi cuenta
    Y usa el metodo guardado sin volver a solicitar el numero de tarjeta ni el CVV
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

**Cobertura automatizada:** metodo guardado, reserva sin metodo guardado, tarjeta invalida y comprobacion de que solo se almacena titular/ultimos cuatro digitos. La automatizacion de interaccion modal en navegador queda pendiente.

### HU-02 - Calendario dinamico de disponibilidad

**Criterios de aceptacion**

1. La API calcula estados por fecha: `libre`, `parcial`, `ocupado` o `pasado`, usando las franjas diarias 09:00-21:00.
2. La respuesta identifica el recurso, cuenta franjas libres y considera reservas activas y bloqueos.
3. La reserva directa en API rechaza cruces con reservas y bloqueos; la UI refresca eventos.
4. Los rangos invertidos, fechas invalidas y consultas mayores al limite se rechazan.

```gherkin
Caracteristica: Consulta dinamica de disponibilidad

  Escenario: Mostrar dias con horarios disponibles y ocupados
    Dado un recurso con horarios operativos definidos
    Y existen reservas y bloqueos para algunos horarios
    Cuando consulto el calendario del recurso
    Entonces los dias libres, parciales, ocupados y pasados se distinguen
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

**Cobertura automatizada:** dias parcialmente ocupados, dias completamente bloqueados, rango invalido y rechazo de bloqueos en el endpoint de reserva. La presentacion visual y refresco del calendario requieren validacion E2E de navegador.

### HU-03 - Graficos de prevision de demanda para administrador

**Criterios de aceptacion**

1. Solo usuarios `staff` pueden abrir el panel y consultar la API de demanda.
2. La respuesta incluye 12 semanas historicas y 4 semanas futuras, mas el promedio por dia y sugerencia de precio.
3. El metodo es reproducible: media movil de 3 semanas; las canceladas no cuentan como demanda activa.
4. Un recurso sin historial devuelve estructuras validas con previsiones de cero y no expone datos a usuarios sin permiso.

```gherkin
Caracteristica: Prevision de demanda del administrador

  Escenario: Consultar la prevision con permiso administrativo
    Dado que inicio sesion con una cuenta administradora
    Y existen reservas historicas para el recurso
    Cuando abro el panel y selecciono el recurso
    Entonces se muestra un grafico con la demanda historica y la prevista
    Y la API entrega 12 semanas historicas y 4 semanas previstas para ese recurso

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

**Cobertura automatizada:** permisos del panel/API, render del panel, forma de la respuesta y longitudes de series. El render de los graficos Chart.js y el cambio de recurso requieren E2E/manual en navegador.

## 3. Historias adicionales

En la version actual del repositorio, H4 y H5 corresponden a Mis reservas/cancelaciones y correo de confirmacion.

### HU-04 - Consultar y cancelar mis reservas

```gherkin
Caracteristica: Consultar y administrar mis reservas

  Escenario: Consultar las proximas reservas propias
    Dado que inicio sesion y tengo una reserva futura
    Cuando abro "Mis reservas"
    Entonces veo la reserva con recurso, fecha, horario y estado de pago
    Y no veo reservas de otros usuarios

  Escenario: Cancelar una reserva futura propia
    Dado que tengo una reserva futura confirmada
    Cuando solicito cancelar esa reserva
    Entonces su estado cambia a cancelada
    Y deja de bloquear el horario

  Escenario: Impedir cancelar una reserva de otra persona
    Dado que inicio sesion con mi cuenta
    Y existe una reserva futura propiedad de otro usuario
    Cuando intento cancelarla
    Entonces el sistema deniega la operacion
    Y la reserva permanece confirmada
```

### HU-05 - Correo de confirmacion de reserva

```gherkin
Caracteristica: Enviar confirmacion de reserva

  Escenario: Enviar correo despues de crear una reserva
    Dado que el usuario autenticado tiene un correo configurado
    Y el recurso y el horario estan disponibles
    Cuando se confirma la reserva
    Entonces se envia un correo con recurso, fecha, horario y total
    Y la reserva permanece creada aunque falle el envio del correo

  Escenario: Cuenta sin correo
    Dado que el usuario autenticado no tiene correo configurado
    Cuando se confirma la reserva
    Entonces la reserva se conserva
    Y el sistema registra que no pudo enviar la confirmacion
```

**Cobertura automatizada de H4/H5:** visualizacion de reservas propias, aislamiento de propietario, cancelacion autorizada/no autorizada y composicion/envio de correo en backend de pruebas.

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

| ID | HU | Preparacion y accion | Resultado automatizado/esperado |
|---|---|---|---|
| INT-01 | H1 | Usuario autenticado reserva con metodo guardado. | HTTP 200; reserva pagada asociada a usuario/recurso; solo se guarda last4; se envia confirmacion. |
| INT-02 | H1 | Seleccionar metodo guardado inexistente o tarjeta invalida. | HTTP 400; no se persiste reserva ni datos de tarjeta. |
| INT-03 | H2 | Consultar fecha parcialmente ocupada y fecha bloqueada todo el dia. | API calcula estado `parcial`/`ocupado` y conteo esperado de franjas libres. |
| INT-04 | H2 | Crear una reserva cruzando otra reserva o bloqueo. | HTTP 409; no se crea una fila nueva. |
| INT-05 | H2 | Enviar JSON/fecha/intervalo/rango incorrectos. | Error 400 controlado; cero reservas nuevas. |
| INT-06 | H3 | Usuario sin rol staff solicita panel o API de demanda. | Acceso denegado (403 en API; panel protegido). |
| INT-07 | H3 | Usuario staff consulta recurso sin historial. | JSON con 12 semanas historicas y 4 previstas con valores cero; panel renderiza. |
| INT-08 | H4 | Usuario consulta y cancela su proxima reserva. | Solo ve sus reservas; cambio de estado persistido y horario reservable nuevamente. |
| INT-09 | H4 | Intentar cancelar reserva de otro usuario. | 403; reserva permanece confirmada. |
| INT-10 | H5 | Crear reserva con usuario con correo y simular fallo de envio. | Con envio correcto se crea correo resumen; con fallo, reserva persiste y API informa correo no enviado. |
| UI-01 | H1/H2 | Abrir calendario, seleccionar dia/franja y confirmar pago. | Pendiente E2E: modal, refresco, estados visuales y flujo de navegador. |
| UI-02 | H3 | Cambiar recurso en selector del panel. | Pendiente E2E: los graficos Chart.js actualizan sin error. |
| UI-03 | H4/H5 | Consultar reservas y verificar correo recibido. | Pendiente prueba de navegador/casilla del entorno de demo. |

Para no hacer tests fragiles, comprobar el contrato de API y el estado de la base de datos, no el texto exacto de alertas salvo que sea requisito. El endpoint de reserva responde 200 al crear, 403 a usuarios anonimos, 400 a payloads o fechas invalidas, 404 a recursos inexistentes y 409 a conflictos.

## 5. Hallazgos y evidencia de IA

**No se encontro en el repositorio historial de prompts, respuestas de IA, diffs rechazados ni registros de ejecucion anteriores.** Por tanto, no es correcto atribuir los defectos siguientes a la IA sin contrastarlos con evidencia del equipo. Son hallazgos del QA local, no afirmaciones sobre la autoria.

| Ref. | Observacion del proceso QA | Correccion/prueba de regresion | Evidencia de IA |
|---|---|---|---|
| QA-F01 | La rama QA inicial no incluia H1-H5 porque se habia partido de un `main` antiguo. | Se actualizo con `origin/main` y se reescribio el alcance/matriz para las historias reales. | No atribuible a IA; fallo de sincronizacion/version del repositorio. |
| QA-F02 | En la revision del endpoint nuevo, fin igual/inferior al inicio retornaba conflicto 409, no error de entrada 400. | Se agrego validacion temprana de intervalo y prueba `test_invalid_interval_is_rejected_without_creating_booking`. | No hay prompt/respuesta que permita atribuirlo a IA. |
| QA-F03 | Conflictos al fusionar `qa` con `origin/main` dejaron temporalmente marcadores de merge en `mis_pagos`; la compilacion inicial fallo y evito aprobar el merge roto. | Se resolvio conservando el flujo actualizado de pagos; `compileall`, `check` y suite regresaron a verde. | Error de merge local, no evidencia de respuesta incorrecta de IA. |

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

| HU | Criterios / escenarios | Validacion ejecutada | Evidencia para presentacion | Estado |
|---|---|---|---|---|
| HU-01 Reserva rapida con pago guardado | Seleccion/uso de metodo guardado, rechazo sin metodo, persistencia segura | Pruebas API y modelo: metodo guardado, ausente, tarjeta invalida; reserva y correo | JSON API, fila Booking/PaymentMethod sin PAN/CVV, resultado de test | Backend aprobado; E2E modal pendiente |
| HU-02 Calendario dinamico | Estados del dia, ocupacion/bloqueos, rangos invalidos y rechazo server-side | API de disponibilidad parcial/ocupada y conflicto con reserva/bloqueo | JSON con `estado/libres`, request de rechazo, captura del calendario | Logica backend aprobada; E2E visual/refresco pendiente |
| HU-03 Pronostico de demanda | Permisos, historico 12 semanas, forecast 4 semanas, recurso sin historial | Acceso staff/no staff, forma de JSON, valores vacios, media movil | JSON esperado, rol, panel HTML/captura del grafico | API/panel backend aprobado; render Chart.js pendiente en navegador |
| HU-04 Mis reservas | Aislamiento por usuario, cancelacion propia, prohibir cancelar de otro, liberar franja | Client de Django y comprobacion del estado en BD | Usuario, response/codigo, estado antes/despues, resultado de tests | Backend aprobado; flujo visual pendiente |
| HU-05 Correo de confirmacion | Resumen correcto, correo sin destinatario/fallo de correo sin perder reserva | Backend de correo en pruebas y fallo simulado | Mensaje capturado, destinatario, resultado JSON y Booking persistido | Backend aprobado; entrega en entorno SMTP real pendiente |

**Criterio de salida para la demo:** las cinco HU tienen cobertura backend automatizada en la version actual, pero no estan validadas completamente de extremo a extremo hasta ejecutar las comprobaciones de navegador y, para H5, verificar entrega real en el entorno acordado. Adjuntar la salida de pruebas vinculada al commit que se presente.
