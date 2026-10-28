import json
from functools import wraps
from datetime import date, datetime, timedelta, time
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone
from django.utils.dateformat import format as date_format
from django.utils.dateparse import parse_datetime
from django.utils.http import url_has_allowed_host_and_scheme
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from .models import Resource, Booking, Availability, PaymentMethod
from .disponibilidad import estado_dias, motivo_no_disponible
from .pagos import precio_reserva, validar_tarjeta
from .correos import enviar_confirmacion
from .demanda import AJUSTE_PRECIO, UMBRAL_ALTO, UMBRAL_BAJO, VENTANA_MEDIA_MOVIL, datos_demanda


# Horario por defecto (si no hay Availability definida)
DEFAULT_START = time(9, 0)   # 09:00
DEFAULT_END = time(21, 0)    # 21:00

# Máximo de días que se pueden consultar de una sola vez en la API de disponibilidad
MAX_DIAS_CONSULTA = 62

# Máximo de semanas que se puede repetir una reserva
MAX_SEMANAS_REPETICION = 12

# Semanas hacia adelante que se muestran en la previsión de demanda
SEMANAS_PREVISION = 4


def calendario(request, resource_id):
    """
    Muestra un calendario semanal de reservas para un recurso.
    """
    resource = get_object_or_404(Resource, id=resource_id)

    hoy = datetime.today()
    inicio_semana = hoy - timedelta(days=hoy.weekday())  # Lunes
    dias_semana = [inicio_semana + timedelta(days=i) for i in range(7)]

    reservas = Booking.objects.activas().filter(
        resource=resource,
        start_time__date__gte=inicio_semana,
        start_time__date__lte=inicio_semana + timedelta(days=6)
    ).order_by('start_time')

    reservas_por_dia = {date_format(dia, 'Y-m-d'): [] for dia in dias_semana}
    for reserva in reservas:
        clave = date_format(reserva.start_time, 'Y-m-d')
        reservas_por_dia[clave].append(reserva)

    return render(request, 'reservas/calendario.html', {
        'resource': resource,
        'dias_semana': dias_semana,
        'reservas_por_dia': reservas_por_dia,
    })


def calendario_navegable(request, resource_id):
    """
    Calendario semanal con botones de semana anterior/siguiente.
    """
    resource = get_object_or_404(Resource, id=resource_id)

    hoy = datetime.today()
    delta = 0
    if request.GET.get('week') == 'prev':
        delta = -7
    elif request.GET.get('week') == 'next':
        delta = 7

    inicio_semana = (hoy - timedelta(days=hoy.weekday())) + timedelta(days=delta)
    dias_semana = [inicio_semana + timedelta(days=i) for i in range(7)]

    reservas = Booking.objects.activas().filter(
        resource=resource,
        start_time__date__gte=inicio_semana,
        start_time__date__lte=inicio_semana + timedelta(days=6)
    ).order_by('start_time')

    reservas_por_dia = {date_format(dia, 'Y-m-d'): [] for dia in dias_semana}
    for reserva in reservas:
        clave = date_format(reserva.start_time, 'Y-m-d')
        reservas_por_dia[clave].append(reserva)

    return render(request, 'reservas/calendario.html', {
        'resource': resource,
        'dias_semana': dias_semana,
        'reservas_por_dia': reservas_por_dia,
    })


@ensure_csrf_cookie
def calendario_full(request, resource_id):
    """
    Calendario interactivo con FullCalendar.
    """
    resource = get_object_or_404(Resource, id=resource_id)

    bloqueos = Availability.objects.filter(resource=resource)

    # Lista de bloqueos (rojo)
    bloqueos_json = [
        {
            "start": bloqueo.start_time.isoformat(),
            "end": bloqueo.end_time.isoformat(),
            "title": "Bloqueado",
            "extendedProps": {"tipo": "bloqueo"},
        }
        for bloqueo in bloqueos
    ]

    return render(request, 'reservas/calendario_full.html', {
        'resource': resource,
        'bloqueos_json': json.dumps(bloqueos_json),
        'is_authenticated': request.user.is_authenticated,
        'metodo_guardado': (
            PaymentMethod.objects.filter(user=request.user).first()
            if request.user.is_authenticated else None
        ),
    })



def api_crear_reserva(request):
    """
    Endpoint para crear una nueva reserva, con soporte para repeticiones semanales.
    Primero se valida cada semana y solo si todas están libres se crean las reservas.

    El pago llega en el campo payment: {"method": "saved"} usa el método guardado,
    {"method": "card", "card": {...}, "save_card": true} usa una tarjeta nueva y
    {"method": "later"} deja la reserva sin pagar.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Debes iniciar sesión para reservar.'}, status=403)

    try:
        data = json.loads(request.body)
        resource_id = int(data.get('resource_id'))
        start_time = parse_datetime(data.get('start_time') or '')
        end_time = parse_datetime(data.get('end_time') or '')
        repeat_weeks = int(data.get('repeat_weeks', 0))
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Datos de reserva no válidos.'}, status=400)

    if start_time is None or end_time is None:
        return JsonResponse({'success': False, 'error': 'Fechas de reserva no válidas.'}, status=400)
    if end_time <= start_time:
        return JsonResponse({'success': False, 'error': 'El intervalo de fechas no es válido.'}, status=400)
    resource = Resource.objects.filter(id=resource_id).first()
    if resource is None:
        return JsonResponse({'success': False, 'error': 'El recurso no existe.'}, status=404)
    if not 0 <= repeat_weeks <= MAX_SEMANAS_REPETICION:
        return JsonResponse({
            'success': False,
            'error': f'Las semanas a repetir deben estar entre 0 y {MAX_SEMANAS_REPETICION}.'
        }, status=400)

    if timezone.is_naive(start_time):
        start_time = timezone.make_aware(start_time)
    if timezone.is_naive(end_time):
        end_time = timezone.make_aware(end_time)

    pago = data.get('payment') if isinstance(data.get('payment'), dict) else {}
    metodo = pago.get('method', 'later')
    last4 = ''
    tarjeta = None
    if metodo == 'saved':
        guardado = PaymentMethod.objects.filter(user=request.user).first()
        if guardado is None:
            return JsonResponse({'success': False, 'error': 'No tienes un método de pago guardado.'}, status=400)
        last4 = guardado.last4
    elif metodo == 'card':
        tarjeta, error = validar_tarjeta(pago.get('card'))
        if error:
            return JsonResponse({'success': False, 'error': error}, status=400)
        last4 = tarjeta['last4']
    elif metodo != 'later':
        return JsonResponse({'success': False, 'error': 'Método de pago no válido.'}, status=400)

    franjas = [
        (start_time + timedelta(weeks=i), end_time + timedelta(weeks=i))
        for i in range(repeat_weeks + 1)
    ]

    for i, (inicio, fin) in enumerate(franjas):
        motivo = motivo_no_disponible(resource_id, inicio, fin)
        if motivo:
            if repeat_weeks:
                motivo = f'Semana {i + 1} ({timezone.localtime(inicio):%d/%m/%Y %H:%M}): {motivo}'
            return JsonResponse({'success': False, 'error': motivo}, status=409)

    precio = precio_reserva(resource, start_time, end_time)
    with transaction.atomic():
        for inicio, fin in franjas:
            Booking.objects.create(
                user=request.user,
                resource=resource,
                start_time=inicio,
                end_time=fin,
                price=precio,
                paid=metodo != 'later',
                payment_last4=last4,
            )
        if tarjeta and pago.get('save_card'):
            PaymentMethod.objects.update_or_create(
                user=request.user,
                defaults={'holder': tarjeta['holder'], 'last4': tarjeta['last4']},
            )

    # El correo se envía después de guardar: si falla, la reserva queda igual
    total = precio * len(franjas)
    correo_enviado = enviar_confirmacion(request.user, resource, franjas, total, last4)

    return JsonResponse({
        'success': True,
        'reservas': [{'start': i.isoformat(), 'end': f.isoformat()} for i, f in franjas],
        'total': str(total),
        'pagado': metodo != 'later',
        'tarjeta': last4,
        'correo_enviado': correo_enviado,
    })


def api_disponibilidad(request, resource_id):
    """
    Devuelve el estado (libre, parcial, ocupado o pasado) de cada día entre
    los parámetros start y end (fechas ISO). Lo usa el calendario para pintar los días.
    """
    get_object_or_404(Resource, id=resource_id)
    try:
        desde = date.fromisoformat(request.GET.get('start', '')[:10])
        hasta = date.fromisoformat(request.GET.get('end', '')[:10])
    except ValueError:
        return JsonResponse({'error': 'Los parámetros start y end deben ser fechas ISO.'}, status=400)

    if hasta < desde or (hasta - desde).days > MAX_DIAS_CONSULTA:
        return JsonResponse({'error': 'Rango de fechas no válido.'}, status=400)

    return JsonResponse({
        'resource_id': resource_id,
        'dias': estado_dias(resource_id, desde, hasta),
    })


def staff_requerido(vista):
    """Solo deja pasar a usuarios staff: quien no inició sesión va al login y los demás reciben 403."""
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_staff:
            raise PermissionDenied
        return vista(request, *args, **kwargs)
    return envoltura


@staff_requerido
def panel_demanda(request):
    """
    Panel para el administrador con gráficos de la demanda histórica y su previsión.
    """
    recursos = Resource.objects.order_by('name')
    resumen = [datos_demanda(recurso) for recurso in recursos]
    return render(request, 'reservas/demanda.html', {
        'recursos': recursos,
        'resumen': resumen,
        'semanas_futuras': SEMANAS_PREVISION,
        'ventana': VENTANA_MEDIA_MOVIL,
        'umbral_alto': int(UMBRAL_ALTO * 100),
        'umbral_bajo': int(UMBRAL_BAJO * 100),
        'ajuste': int(AJUSTE_PRECIO * 100),
    })


def api_demanda(request, resource_id):
    """Datos de demanda de un recurso en JSON. Solo para staff."""
    if not (request.user.is_authenticated and request.user.is_staff):
        return JsonResponse({'error': 'Solo el personal administrativo puede ver la demanda.'}, status=403)
    recurso = get_object_or_404(Resource, id=resource_id)
    return JsonResponse(datos_demanda(recurso, semanas_futuras=SEMANAS_PREVISION))


@login_required
def mis_reservas(request):
    """
    Lista las reservas del usuario: las próximas (que se pueden cancelar) y el historial.
    """
    ahora = timezone.now()
    reservas = Booking.objects.filter(user=request.user).select_related('resource')
    proximas = reservas.activas().filter(start_time__gte=ahora).order_by('start_time')
    historial = (
        reservas.exclude(pk__in=proximas.values('pk')).order_by('-start_time')
    )
    return render(request, 'reservas/mis_reservas.html', {
        'proximas': proximas,
        'historial': historial,
    })


@login_required
@require_POST
def cancelar_reserva(request, booking_id):
    """
    Cancela una reserva propia que todavía no empezó. La franja queda libre otra vez.
    """
    reserva = get_object_or_404(Booking, id=booking_id)
    if reserva.user_id != request.user.id:
        raise PermissionDenied
    if reserva.status == Booking.CANCELADA:
        messages.error(request, 'Esa reserva ya estaba cancelada.')
    elif reserva.start_time <= timezone.now():
        messages.error(request, 'No se puede cancelar una reserva que ya empezó o ya pasó.')
    else:
        reserva.status = Booking.CANCELADA
        reserva.cancelled_at = timezone.now()
        reserva.save(update_fields=['status', 'cancelled_at'])
        messages.success(request, 'La reserva se canceló y la franja quedó libre.')
    return redirect('mis_reservas')


@login_required
def mis_pagos(request):
    """
    Página donde el usuario guarda o elimina su método de pago.
    Del formulario solo se guardan el titular y los últimos 4 dígitos.
    """
    if request.method == 'POST':
        if request.POST.get('accion') == 'eliminar':
            PaymentMethod.objects.filter(user=request.user).delete()
            messages.success(request, 'Se eliminó tu método de pago guardado.')
        else:
            tarjeta, error = validar_tarjeta({
                'holder': request.POST.get('holder'),
                'number': request.POST.get('number'),
                'expiry': request.POST.get('expiry'),
                'cvv': request.POST.get('cvv'),
            })
            if error:
                messages.error(request, error)
            else:
                PaymentMethod.objects.update_or_create(
                    user=request.user,
                    defaults={'holder': tarjeta['holder'], 'last4': tarjeta['last4']},
                )
                messages.success(request, 'Tu método de pago se guardó correctamente.')
        return redirect('mis_pagos')

    return render(request, 'reservas/pagos.html', {
        'metodo': PaymentMethod.objects.filter(user=request.user).first(),
    })


def login_view(request):
    """
    Vista para el inicio de sesión de usuarios.
    """
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            siguiente = request.GET.get('next', '')
            if siguiente and url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()}):
                return redirect(siguiente)
            return redirect('/')
        else:
            messages.error(request, "Usuario o contraseña incorrectos.")
    return render(request, 'reservas/login.html')


def logout_view(request):
    """
    Cerrar sesión.
    """
    logout(request)
    return redirect('/login/')

def api_reservas(request, resource_id):
    """
    API que devuelve todas las reservas de un recurso en formato JSON.
    """
    reservas = Booking.objects.activas().filter(resource_id=resource_id).order_by('start_time')
    eventos = [
        {
            "title": f"Reservado por {reserva.user.username}",
            "start": reserva.start_time.isoformat(),
            "end": reserva.end_time.isoformat(),
            "color": "#2563eb",  # Azul (el verde se usa para los días libres)
            "extendedProps": {"tipo": "reserva"},
        }
        for reserva in reservas
    ]
    return JsonResponse(eventos, safe=False)

def home(request):
    """
    Vista principal que muestra todas las pistas (resources).
    """
    resources = Resource.objects.all()  # Obtenemos todas las pistas
    return render(request, 'reservas/home.html', {'resources': resources})
