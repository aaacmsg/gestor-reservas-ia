import json
from datetime import date, datetime, timedelta, time
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.db import transaction
from django.utils import timezone
from django.utils.dateformat import format as date_format
from django.utils.dateparse import parse_datetime
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .models import Resource, Booking, Availability
from .disponibilidad import estado_dias, motivo_no_disponible


# Horario por defecto (si no hay Availability definida)
DEFAULT_START = time(9, 0)   # 09:00
DEFAULT_END = time(21, 0)    # 21:00

# Máximo de días que se pueden consultar de una sola vez en la API de disponibilidad
MAX_DIAS_CONSULTA = 62

# Máximo de semanas que se puede repetir una reserva
MAX_SEMANAS_REPETICION = 12


def calendario(request, resource_id):
    """
    Muestra un calendario semanal de reservas para un recurso.
    """
    resource = get_object_or_404(Resource, id=resource_id)

    hoy = datetime.today()
    inicio_semana = hoy - timedelta(days=hoy.weekday())  # Lunes
    dias_semana = [inicio_semana + timedelta(days=i) for i in range(7)]

    reservas = Booking.objects.filter(
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

    reservas = Booking.objects.filter(
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
    })



def api_crear_reserva(request):
    """
    Endpoint para crear una nueva reserva, con soporte para repeticiones semanales.
    Primero se valida cada semana y solo si todas están libres se crean las reservas.
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
    if not Resource.objects.filter(id=resource_id).exists():
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

    with transaction.atomic():
        for inicio, fin in franjas:
            Booking.objects.create(
                user=request.user,
                resource_id=resource_id,
                start_time=inicio,
                end_time=fin
            )

    return JsonResponse({
        'success': True,
        'reservas': [{'start': i.isoformat(), 'end': f.isoformat()} for i, f in franjas]
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
    reservas = Booking.objects.filter(resource_id=resource_id).order_by('start_time')
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


