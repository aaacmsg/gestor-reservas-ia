from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

from .disponibilidad import HORA_FIN, HORA_INICIO
from .models import Booking

# Horas que tiene un recurso disponibles en una semana (7 días de 09:00 a 21:00)
HORAS_POR_SEMANA = (HORA_FIN - HORA_INICIO) * 7

# Cuántas semanas se promedian para calcular la previsión
VENTANA_MEDIA_MOVIL = 3

# Si la ocupación prevista pasa el umbral alto se sugiere subir el precio, y si queda
# por debajo del umbral bajo se sugiere bajarlo
UMBRAL_ALTO = 0.5
UMBRAL_BAJO = 0.15
AJUSTE_PRECIO = Decimal('0.10')

NOMBRES_DIAS = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']


def lunes_de(dia):
    return dia - timedelta(days=dia.weekday())


def inicio_del_dia(dia):
    return timezone.make_aware(datetime.combine(dia, time.min), timezone.get_current_timezone())


def horas_reservadas(resource_id, desde, hasta):
    """Devuelve (fecha local, horas) de cada reserva que empieza entre dos fechas."""
    reservas = Booking.objects.activas().filter(
        resource_id=resource_id,
        start_time__gte=inicio_del_dia(desde),
        start_time__lt=inicio_del_dia(hasta),
    ).values_list('start_time', 'end_time')
    return [
        (timezone.localtime(ini).date(), (fin - ini).total_seconds() / 3600)
        for ini, fin in reservas
    ]


def horas_por_semana(resource_id, semanas):
    """Horas reservadas en cada una de las últimas semanas completas (de la más vieja a la más nueva)."""
    lunes_actual = lunes_de(timezone.localdate())
    primera = lunes_actual - timedelta(weeks=semanas)
    totales = defaultdict(float)
    for dia, horas in horas_reservadas(resource_id, primera, lunes_actual):
        totales[lunes_de(dia)] += horas
    lunes = [primera + timedelta(weeks=i) for i in range(semanas)]
    return lunes, [round(totales[l], 1) for l in lunes]


def horas_por_dia_de_semana(resource_id, semanas):
    """Promedio de horas reservadas por cada día de la semana en las últimas semanas completas."""
    lunes_actual = lunes_de(timezone.localdate())
    primera = lunes_actual - timedelta(weeks=semanas)
    totales = [0.0] * 7
    for dia, horas in horas_reservadas(resource_id, primera, lunes_actual):
        totales[dia.weekday()] += horas
    return [round(t / semanas, 1) for t in totales]


def media_movil(valores, semanas_futuras, ventana=VENTANA_MEDIA_MOVIL):
    """
    Previsión con media móvil: cada semana futura es el promedio de las últimas
    `ventana` semanas, y ese resultado se usa para calcular la semana siguiente.
    """
    serie = list(valores)
    prevision = []
    for _ in range(semanas_futuras):
        base = serie[-ventana:]
        siguiente = sum(base) / len(base) if base else 0
        prevision.append(round(siguiente, 1))
        serie.append(siguiente)
    return prevision


def sugerencia_precio(precio_actual, ocupacion_prevista):
    """Sugiere subir, bajar o mantener el precio según la ocupación prevista (0 a 1)."""
    if ocupacion_prevista >= UMBRAL_ALTO:
        accion, factor = 'subir', 1 + AJUSTE_PRECIO
    elif ocupacion_prevista <= UMBRAL_BAJO:
        accion, factor = 'bajar', 1 - AJUSTE_PRECIO
    else:
        accion, factor = 'mantener', Decimal(1)
    return {
        'accion': accion,
        'precio_actual': str(precio_actual),
        'precio_sugerido': str((precio_actual * factor).quantize(Decimal('0.01'))),
    }


def datos_demanda(resource, semanas_historico=12, semanas_futuras=4):
    """Todo lo que necesita el panel para un recurso: histórico, previsión y sugerencia de precio."""
    lunes, historico = horas_por_semana(resource.id, semanas_historico)
    prevision = media_movil(historico, semanas_futuras)
    lunes_futuros = [lunes[-1] + timedelta(weeks=i + 1) for i in range(semanas_futuras)]

    ocupacion_historica = sum(historico) / len(historico) / HORAS_POR_SEMANA if historico else 0
    ocupacion_prevista = sum(prevision) / len(prevision) / HORAS_POR_SEMANA if prevision else 0

    por_dia = horas_por_dia_de_semana(resource.id, semanas_historico)
    dia_flojo = NOMBRES_DIAS[por_dia.index(min(por_dia))]

    return {
        'recurso': {'id': resource.id, 'nombre': resource.name},
        'semanas': [l.strftime('%d/%m') for l in lunes],
        'historico': historico,
        'semanas_futuras': [l.strftime('%d/%m') for l in lunes_futuros],
        'prevision': prevision,
        'dias': NOMBRES_DIAS,
        'promedio_por_dia': por_dia,
        'ocupacion_historica': round(ocupacion_historica * 100, 1),
        'ocupacion_prevista': round(ocupacion_prevista * 100, 1),
        'dia_con_menos_demanda': dia_flojo,
        'sugerencia': sugerencia_precio(resource.price_per_hour, ocupacion_prevista),
    }
