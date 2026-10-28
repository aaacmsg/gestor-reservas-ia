import re
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone


def luhn_valido(numero):
    """Revisa el dígito verificador de la tarjeta (algoritmo de Luhn)."""
    suma = 0
    for i, digito in enumerate(reversed(numero)):
        n = int(digito)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        suma += n
    return suma % 10 == 0


def validar_tarjeta(datos):
    """
    Valida los datos de una tarjeta enviados desde el formulario.
    Devuelve (datos_limpios, error). Del número solo se conservan los últimos 4 dígitos
    y el CVV y la fecha de vencimiento se descartan después de validarlos.
    """
    if not isinstance(datos, dict):
        return None, 'Faltan los datos de la tarjeta.'

    titular = str(datos.get('holder', '')).strip()
    numero = re.sub(r'[\s-]', '', str(datos.get('number', '')))
    vencimiento = str(datos.get('expiry', '')).strip()
    cvv = str(datos.get('cvv', '')).strip()

    if not titular or len(titular) > 100:
        return None, 'Escribe el nombre del titular.'
    if not numero.isdigit() or not 13 <= len(numero) <= 19 or not luhn_valido(numero):
        return None, 'El número de tarjeta no es válido.'
    if not re.fullmatch(r'\d{2}/\d{2}', vencimiento):
        return None, 'El vencimiento debe tener el formato MM/AA.'
    mes, anio = int(vencimiento[:2]), 2000 + int(vencimiento[3:])
    if not 1 <= mes <= 12:
        return None, 'El mes de vencimiento no es válido.'
    hoy = timezone.localdate()
    if (anio, mes) < (hoy.year, hoy.month):
        return None, 'La tarjeta está vencida.'
    if not re.fullmatch(r'\d{3,4}', cvv):
        return None, 'El CVV debe tener 3 o 4 dígitos.'

    return {'holder': titular, 'last4': numero[-4:]}, None


def precio_reserva(resource, inicio, fin):
    """Precio de una reserva: horas reservadas por el precio por hora del recurso."""
    horas = Decimal((fin - inicio) / timedelta(seconds=1)) / Decimal(3600)
    return (horas * resource.price_per_hour).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
