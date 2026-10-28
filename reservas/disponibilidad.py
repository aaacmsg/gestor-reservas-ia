from datetime import datetime, time, timedelta

from django.utils import timezone

from .models import Availability, Booking

# Horario en el que se puede reservar (igual al del calendario)
HORA_INICIO = 9
HORA_FIN = 21


def franjas_del_dia(dia):
    """Devuelve las franjas de una hora de un día (fecha local)."""
    zona = timezone.get_current_timezone()
    franjas = []
    for hora in range(HORA_INICIO, HORA_FIN):
        inicio = timezone.make_aware(datetime.combine(dia, time(hora)), zona)
        franjas.append((inicio, inicio + timedelta(hours=1)))
    return franjas


def hay_bloqueo(resource_id, inicio, fin):
    return Availability.objects.filter(
        resource_id=resource_id,
        start_time__lt=fin,
        end_time__gt=inicio,
    ).exists()


def hay_reserva(resource_id, inicio, fin):
    return Booking.objects.filter(
        resource_id=resource_id,
        start_time__lt=fin,
        end_time__gt=inicio,
    ).exists()


def motivo_no_disponible(resource_id, inicio, fin):
    """Devuelve el motivo por el que una franja no se puede reservar, o None."""
    if fin <= inicio:
        return 'La hora de fin debe ser mayor a la de inicio.'
    if inicio < timezone.now():
        return 'No se puede reservar en una fecha pasada.'
    if hay_bloqueo(resource_id, inicio, fin):
        return 'La franja está bloqueada por el administrador.'
    if hay_reserva(resource_id, inicio, fin):
        return 'Ya existe una reserva en esa franja.'
    return None


def estado_dias(resource_id, desde, hasta):
    """
    Calcula el estado de cada día entre dos fechas (incluidas).

    Estados:
      pasado  - el día ya terminó o no quedan franjas por delante
      libre   - todas las franjas siguen disponibles
      parcial - hay franjas libres y franjas ocupadas o bloqueadas
      ocupado - no queda ninguna franja libre
    """
    zona = timezone.get_current_timezone()
    rango_ini = timezone.make_aware(datetime.combine(desde, time.min), zona)
    rango_fin = timezone.make_aware(datetime.combine(hasta + timedelta(days=1), time.min), zona)

    # Se consultan reservas y bloqueos una sola vez para todo el rango
    reservas = list(Booking.objects.filter(
        resource_id=resource_id,
        start_time__lt=rango_fin,
        end_time__gt=rango_ini,
    ).values_list('start_time', 'end_time'))
    bloqueos = list(Availability.objects.filter(
        resource_id=resource_id,
        start_time__lt=rango_fin,
        end_time__gt=rango_ini,
    ).values_list('start_time', 'end_time'))
    ocupadas = reservas + bloqueos

    ahora = timezone.now()
    dias = []
    dia = desde
    while dia <= hasta:
        franjas = [f for f in franjas_del_dia(dia) if f[0] >= ahora]
        libres = sum(
            1 for ini, fin in franjas
            if not any(o_ini < fin and o_fin > ini for o_ini, o_fin in ocupadas)
        )
        if not franjas:
            estado = 'pasado'
        elif libres == len(franjas):
            estado = 'libre'
        elif libres == 0:
            estado = 'ocupado'
        else:
            estado = 'parcial'
        dias.append({
            'fecha': dia.isoformat(),
            'estado': estado,
            'libres': libres,
            'total': len(franjas),
        })
        dia += timedelta(days=1)
    return dias
