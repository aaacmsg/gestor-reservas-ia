import json
from datetime import datetime, timedelta, time
from django.db import transaction
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateformat import format as date_format
from django.utils.dateparse import parse_datetime
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .models import Resource, Booking, Availability
from .models import Resource


# Horario por defecto (si no hay Availability definida)
DEFAULT_START = time(9, 0)   # 09:00
DEFAULT_END = time(21, 0)    # 21:00


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


def calendario_full(request, resource_id):
    """
    Calendario interactivo con FullCalendar.
    """
    resource = get_object_or_404(Resource, id=resource_id)

    reservas = Booking.objects.filter(resource=resource).order_by('start_time')
    bloqueos = Availability.objects.filter(resource=resource)

    # Lista de reservas
    reservas_json = [
        {
            "start": reserva.start_time.isoformat(),
            "end": reserva.end_time.isoformat(),
            "title": f"Reservado por {reserva.user.username}",
            "color": "#10b981",  # Verde reservas
        }
        for reserva in reservas
    ]

    # Lista de bloqueos (rojo)
    bloqueos_json = [
        {
            "start": bloqueo.start_time.isoformat(),
            "end": bloqueo.end_time.isoformat(),
        }
        for bloqueo in bloqueos
    ]

    return render(request, 'reservas/calendario_full.html', {
        'resource': resource,
        'reservas_json': json.dumps(reservas_json),
        'bloqueos_json': json.dumps(bloqueos_json),
        'is_authenticated': request.user.is_authenticated,
    })



@csrf_exempt
def api_crear_reserva(request):
    """
    Endpoint para crear una nueva reserva, con soporte para repeticiones semanales.
    """
    if request.method == 'POST':
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'error': 'Debes iniciar sesión para reservar.'}, status=403)
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({'success': False, 'error': 'El cuerpo debe contener JSON válido.'}, status=400)

        if not isinstance(data, dict):
            return JsonResponse({'success': False, 'error': 'El cuerpo debe ser un objeto JSON.'}, status=400)

        resource_id = data.get('resource_id')
        start_value = data.get('start_time')
        end_value = data.get('end_time')
        repeat_weeks = data.get('repeat_weeks', 0)

        if isinstance(resource_id, bool) or not str(resource_id or '').isdigit():
            return JsonResponse({'success': False, 'error': 'El recurso indicado no es válido.'}, status=400)
        if not isinstance(start_value, str) or not isinstance(end_value, str):
            return JsonResponse({'success': False, 'error': 'La fecha de inicio y fin son obligatorias.'}, status=400)
        start_time = parse_datetime(start_value)
        end_time = parse_datetime(end_value)
        if start_time is None or end_time is None or end_time <= start_time:
            return JsonResponse({'success': False, 'error': 'El intervalo de fechas no es válido.'}, status=400)
        if isinstance(repeat_weeks, bool) or not isinstance(repeat_weeks, int) or repeat_weeks < 0:
            return JsonResponse({'success': False, 'error': 'La repetición debe ser un entero no negativo.'}, status=400)

        try:
            resource = Resource.objects.get(pk=resource_id)
        except Resource.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'El recurso indicado no existe.'}, status=404)

        occurrences = [
            (start_time + timedelta(weeks=week), end_time + timedelta(weeks=week))
            for week in range(repeat_weeks + 1)
        ]

        with transaction.atomic():
            for week, (start, end) in enumerate(occurrences):
                has_booking_conflict = Booking.objects.filter(
                    resource=resource,
                    start_time__lt=end,
                    end_time__gt=start
                ).exists()
                has_block_conflict = Availability.objects.filter(
                    resource=resource,
                    start_time__lt=end,
                    end_time__gt=start
                ).exists()
                if has_booking_conflict or has_block_conflict:
                    return JsonResponse({
                        'success': False,
                        'error': f'Conflicto: el horario de la semana {week + 1} no está disponible.'
                    }, status=409)

            for start, end in occurrences:
                Booking.objects.create(
                    user=request.user,
                    resource=resource,
                    start_time=start,
                    end_time=end
                )

        return JsonResponse({
            'success': True,
            'reservas': [
                {'start': start.isoformat(), 'end': end.isoformat()}
                for start, end in occurrences
            ]
        })
    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)


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
            "color": "#10b981",  # Verde
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

