# Análisis del proyecto existente

Este documento resume lo que se revisó del proyecto antes de pedirle cambios a la IA. La idea fue entender cómo está armado y qué problemas tiene, para no modificar a ciegas.

## Qué es la aplicación

Sistema web hecho con Django 5 para reservar pistas o salas. Tiene login, un listado de recursos en la página de inicio y un calendario con FullCalendar donde el usuario selecciona una franja para reservar. La base de datos es SQLite.

## Estructura

| Archivo | Para qué sirve |
|---|---|
| `gestor_reservas/settings.py` | Configuración general (zona horaria UTC, SQLite, app `reservas`) |
| `gestor_reservas/urls.py` | Rutas principales, incluye las de `reservas` |
| `reservas/models.py` | Modelos `Resource`, `Availability` (bloqueos) y `Booking` |
| `reservas/views.py` | Vistas del calendario, API para crear reservas, login y logout |
| `reservas/urls.py` | Rutas de la app |
| `reservas/admin.py` | Registro de los modelos en el admin |
| `reservas/templates/reservas/` | `home`, `login`, `calendario` y `calendario_full` |
| `reservas/management/commands/crear_reservas_demo.py` | Comando para cargar datos de prueba |

## Cómo funciona hoy una reserva

1. El usuario inicia sesión y entra al calendario de un recurso (`/calendario_full/<id>/`).
2. Selecciona una franja y el navegador pregunta cuántas semanas repetir.
3. El navegador llama a `POST /api/reservas/crear/` con recurso, inicio, fin y semanas.
4. La vista revisa si hay solapamiento con otra reserva y crea una `Booking` por cada semana.

## Problemas encontrados

1. **Los bloqueos no se validan en el servidor.** El README dice que el sistema valida bloqueos, pero `api_crear_reserva` solo compara contra otras reservas. Solo el JavaScript del calendario avisa, así que una petición directa a la API puede reservar una franja bloqueada.
2. **Las reservas recurrentes se crean a medias.** Si la semana 3 tiene conflicto, las semanas 1 y 2 ya quedaron guardadas y el usuario recibe un error.
3. **No se rechazan fechas pasadas ni franjas con fin antes del inicio.**
4. **La API de crear reserva usa `@csrf_exempt`.** Se apoya solo en la sesión, sin protección CSRF.
5. **El calendario no distingue días libres de ocupados.** Solo pinta las reservas y los bloqueos como eventos. Hay que ir franja por franja para saber si hay espacio.
6. **El calendario usa una lista de reservas cargada al abrir la página.** Después de crear una reserva esa lista queda vieja y el aviso de "ya reservado" no se actualiza hasta recargar.
7. **No existe ningún concepto de pago ni de precio.** Las historias de usuario piden guardar datos de pago y ajustar precios, así que hay que agregarlo.
8. **No hay forma de cancelar una reserva.** Además `Booking` tiene `unique_together` por recurso, inicio y fin, lo que impediría volver a reservar una franja cancelada si la cancelación se hace con un estado.
9. **No se envía ningún correo al reservar.**
10. **Zona horaria en UTC.** El calendario muestra la hora local del navegador, pero el servidor trabaja en UTC. Para calcular días libres y ocupados en el servidor hay que usar la hora local de Panamá.
11. **`base.html` no se usa y está roto** (usa `{% static %}` sin cargarlo y apunta a un css que no existe).
12. **El comando `crear_reservas_demo` borra todas las reservas** antes de crear las de prueba.

## Plan de trabajo

Se siguen los issues H1 a H5 del repositorio, uno por rama y un Pull Request por cada uno. Como varios tocan las mismas funciones (`api_crear_reserva`, `calendario_full.html` y los modelos), las ramas van una encima de la otra en este orden:

| Orden | Issue | Rama | Cambio principal |
|---|---|---|---|
| 1 | H2 | `feature/H2-calendario-disponibilidad` | API de disponibilidad, colores por día, selección bloqueada, validación de bloqueos |
| 2 | H1 | `feature/H1-pago-guardado` | Precio por hora, método de pago guardado, reserva en un paso |
| 3 | H3 | `feature/H3-prevision-demanda` | Panel de demanda solo para staff con gráficos y previsión |
| 4 | H4 | `feature/H4-mis-reservas` | Página de mis reservas y cancelación con estado |
| 5 | H5 | `feature/H5-correo-confirmacion` | Correo de confirmación al reservar |

## Reglas que se fijaron para el trabajo con la IA

- Antes de cada cambio se lee el código que se va a tocar.
- Se hacen cambios pequeños, un commit por cosa.
- Los datos de tarjeta completos nunca se guardan: solo titular y últimos 4 dígitos.
- Cada cambio se prueba a mano en la aplicación corriendo antes de hacer commit.
