import logging

from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)


def armar_mensaje(usuario, recurso, franjas, total, last4):
    """Texto del correo de confirmación con recurso, fecha, hora y total."""
    lineas = [
        f"Hola {usuario.username},",
        "",
        "Tu reserva quedó confirmada.",
        "",
        f"Recurso: {recurso.name}",
    ]
    for inicio, fin in franjas:
        inicio, fin = timezone.localtime(inicio), timezone.localtime(fin)
        lineas.append(f"Fecha: {inicio:%d/%m/%Y}  Hora: {inicio:%H:%M} a {fin:%H:%M}")
    lineas.append("")
    lineas.append(f"Total: ${total}")
    lineas.append(f"Pago: tarjeta terminada en {last4}" if last4 else "Pago: pendiente en el lugar")
    lineas.append("")
    lineas.append("Gracias por reservar.")
    return "\n".join(lineas)


def enviar_confirmacion(usuario, recurso, franjas, total, last4=''):
    """
    Envía el correo de confirmación. Devuelve True si se envió.
    Si el usuario no tiene correo o el envío falla no se lanza error, porque la reserva
    ya se guardó y no debe perderse por un problema con el correo.
    """
    if not usuario.email:
        logger.warning("El usuario %s no tiene correo, no se envió la confirmación.", usuario.username)
        return False
    try:
        send_mail(
            subject=f"Confirmación de reserva - {recurso.name}",
            message=armar_mensaje(usuario, recurso, franjas, total, last4),
            from_email=None,  # usa DEFAULT_FROM_EMAIL
            recipient_list=[usuario.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("No se pudo enviar la confirmación de la reserva a %s.", usuario.email)
        return False
    return True
