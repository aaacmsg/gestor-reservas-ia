# AI Development Log

Registro del uso de la IA durante el desarrollo de las historias H1 a H5. Solo se anotan las interacciones que cambiaron algo importante.

**Herramienta usada:** Claude Code (modelo Sonnet 5.5) en el escritorio, trabajando directamente sobre el repositorio.

## Registro principal

| Actividad | Herramienta IA | Qué se solicitó | Resultado | Decisión humana |
|---|---|---|---|---|
| Arquitectura | Claude Code | Leer modelos, vistas, urls y plantillas y listar problemas antes de cambiar código | 12 problemas, entre ellos que los bloqueos no se validan en el servidor y que las reservas recurrentes se guardan a medias | Aceptada. Quedó en `docs/ANALISIS.md` |
| Planificación | Claude Code | Ordenar los issues H1 a H5 en ramas | Propuso ramas encadenadas (H2, H1, H3, H4, H5) porque todas tocan `api_crear_reserva` y el calendario | Aceptada |
| Código H2 | Claude Code | Endpoint de disponibilidad por día y validación de bloqueos en el servidor | Funcionó. El mensaje decía "Conflicto en la semana 1" aunque la reserva no fuera recurrente | Modificada: solo se nombra la semana si hay repetición |
| Código H2 | Claude Code | Pintar los días libres y ocupados en el calendario | Los fondos con hora no se ven en la vista de mes y la grilla de la semana se estiraba | Corregida: se envían dos fondos por día y se fijó la altura automática |
| Debug H2 | Claude Code | Averiguar por qué el clic en un día no abría la semana | Primero cambió `dateClick` por `select` y luego culpó a la caché de plantillas. La causa real era el script de prueba, que hacía clic sobre una reserva | Diagnóstico incorrecto. El cambio a `select` se dejó porque funciona |
| Diseño H1 | Claude Code | Cómo guardar el método de pago respetando "solo últimos 4 y titular" | Modelo `PaymentMethod` con titular y últimos 4. El número, vencimiento y CVV se validan y se descartan | Aceptada |
| Código H1 | Claude Code | Ventana de reserva con pago en un paso | Funcionó en la prueba: tarjeta inválida, guardar, reservar con la guardada y eliminar | Aceptada |
| Migración H1 | Claude Code | Crear la migración 0002 | Incluyó un cambio de `Availability` que no era de este issue (el modelo ya tenía un `verbose_name` que no estaba en la migración inicial) | Aceptada. Quedó explicado en el commit |
| Diseño H3 | Claude Code | Método de previsión de demanda | Media móvil de 3 semanas sobre horas reservadas, fácil de explicar | Aceptada |
| Código H3 | Claude Code | Comando para cargar historial de prueba | La primera versión tenía una expresión de rebanado difícil de leer | Modificada: se separó en dos líneas |
| Resultado H3 | Claude Code | Sugerencia de precio según la ocupación | Los umbrales de 50% y 15% son valores elegidos para la demo, no salen de datos reales | Aceptada. Quedan como constantes en `demanda.py` |
| Diseño H4 | Claude Code | Cómo cancelar sin perder historial | Estado `cancelada` en vez de borrar. La restricción única pasa a valer solo para reservas confirmadas | Aceptada |
| Código H4 | Claude Code | Excluir las canceladas de todas las consultas | Método `activas()` usado en las consultas de solapamiento, disponibilidad, calendario, API y demanda. Se probó volver a reservar una franja cancelada | Aceptada |
| Código H5 | Claude Code | Correo de confirmación sin romper la reserva si falla | Probado con bandeja en memoria, SMTP caído y usuario sin correo | Aceptada |
| Revisión de QA | QA del proyecto | Revisar el resultado de las 29 pruebas y validar intervalos inválidos en `api_crear_reserva` | Se detectó que `fin <= inicio` terminaba como conflicto HTTP 409 al pasar por `motivo_no_disponible`, aunque es un dato inválido | Aceptada: se añadió una validación explícita antes de consultar el recurso; la API responde HTTP 400 y una prueba de regresión verifica que no se cree la reserva |

## Ejemplos de respuestas incorrectas de la IA

1. **Diagnóstico del clic en el calendario (H2).** Atribuyó la falla al código (`dateClick`) y después a la caché de plantillas. El problema era la prueba, que hacía clic encima de una reserva. Se comprobó cambiando la posición del clic.
2. **Fondos de los días en la vista de mes (H2).** Usó eventos de fondo con hora, que FullCalendar no pinta en la vista de mes. Se vio en la captura y se agregaron fondos de día completo.
3. **Altura de la semana (H2).** El calendario se estiraba más allá de las 21:00. Se arregló con `height: 'auto'`.
4. **Mensaje de conflicto (H2).** Decía "semana 1" en reservas que no se repetían.
5. **Comando de historial (H3).** Una expresión de rebanado (`[-cantidad or len(horas):]`) que daba el resultado correcto pero era difícil de entender.

## Cambios de la IA que se rechazaron o descartaron

- Se descartó borrar la reserva al cancelar, porque el panel de demanda necesita el historial.
- Se descartó la regresión lineal para la previsión y se dejó la media móvil, que es más fácil de explicar.
- Se rechazó la expresión de rebanado del comando de historial y se reescribió.

## Decisiones tomadas por humanos

- Elegir el repositorio de Gestor de Reservas (Django, SQLite).
- Definir las historias H1 a H5 y sus criterios de aceptación en los issues.
- Fijar que del método de pago solo se guardan el titular y los últimos 4 dígitos.
- Trabajar con una rama por issue y un Pull Request por cada una.
- Quitar `@csrf_exempt` de la API de crear reserva, que venía así en el repositorio original.
- Hacer los commits con el usuario propio de GitHub, con mensajes cortos que digan qué se hizo y cómo, sin emojis y sin firma de la IA.
- Analizar el proyecto antes de pedir cambios.

## Cómo se validó cada historia

Cada cambio se probó a mano con la aplicación corriendo, usando un navegador controlado por script y la consola de Django.

| Historia | Qué se comprobó |
|---|---|
| H2 | Colores por día en mes y semana. No se puede seleccionar una franja ocupada o bloqueada. La API rechaza bloqueos, fechas pasadas y reservas recurrentes con conflicto sin dejar nada guardado |
| H1 | Tarjeta inválida muestra error. Guardar, reservar con la guardada en un paso y eliminarla. En la base solo quedan titular y últimos 4 |
| H3 | Usuario sin sesión va al login, usuario normal recibe 403 y staff ve los gráficos. La previsión coincide con el cálculo a mano |
| H4 | Cancelar libera la franja y se puede reservar de nuevo. Cancelar reserva ajena da 403, pasada o ya cancelada no cambia, y GET da 405 |
| H5 | El correo aparece en la consola del servidor. Con SMTP caído la reserva se guarda igual. Sin correo en el usuario no se envía |

## Ramas y Pull Requests

| Issue | Rama | Pull Request |
|---|---|---|
| Análisis y documentación | `docs/analisis-proyecto` | Pull Request propio |
| H2 | `feature/H2-calendario-disponibilidad` | #6 |
| H1 | `feature/H1-pago-guardado` | #7 |
| H3 | `feature/H3-prevision-demanda` | #8 |
| H4 | `feature/H4-mis-reservas` | #9 |
| H5 | `feature/H5-correo-confirmacion` | #10 |

Las ramas de H1, H3, H4 y H5 salen de la anterior de la lista porque modifican las mismas funciones. Cada Pull Request apunta a la rama anterior.
