from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


class Resource(models.Model):
    """Recurso que puede reservarse (pistas, salas, etc.)"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    price_per_hour = models.DecimalField(max_digits=8, decimal_places=2, default=10)

    def __str__(self):
        return self.name


class Availability(models.Model):
    """Horarios disponibles para cada recurso."""
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name='availabilities')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    def __str__(self):
        return f"{self.resource.name} - {self.start_time} a {self.end_time}"
    
    class Meta:
        verbose_name = 'Bloqueo'
        verbose_name_plural = 'Bloqueos'


class BookingQuerySet(models.QuerySet):
    def activas(self):
        """Reservas confirmadas. Las canceladas no ocupan la franja."""
        return self.filter(status=Booking.CONFIRMADA)


class Booking(models.Model):
    """Reserva de un recurso por un usuario."""
    CONFIRMADA = 'confirmada'
    CANCELADA = 'cancelada'
    ESTADOS = [(CONFIRMADA, 'Confirmada'), (CANCELADA, 'Cancelada')]

    objects = BookingQuerySet.as_manager()

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name='bookings')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    paid = models.BooleanField(default=False)
    payment_last4 = models.CharField(max_length=4, blank=True)  # últimos 4 dígitos de la tarjeta usada
    status = models.CharField(max_length=10, choices=ESTADOS, default=CONFIRMADA)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Reserva de {self.resource.name} por {self.user.username}"

    def clean(self):
        """
        Validación para evitar que haya reservas solapadas con la misma franja horaria.
        """
        overlapping = Booking.objects.activas().filter(
            resource=self.resource,
            start_time__lt=self.end_time,
            end_time__gt=self.start_time
        ).exclude(pk=self.pk)  # Excluimos la propia reserva al editar

        if overlapping.exists():
            raise ValidationError("Ya existe una reserva en esta franja horaria.")

    class Meta:
        # La restricción solo vale para reservas confirmadas, así una franja cancelada se puede volver a reservar
        constraints = [
            models.UniqueConstraint(
                fields=['resource', 'start_time', 'end_time'],
                condition=models.Q(status='confirmada'),
                name='reserva_confirmada_unica',
            ),
        ]


class PaymentMethod(models.Model):
    """
    Método de pago guardado de un usuario.
    Solo se guarda el titular y los últimos 4 dígitos, nunca el número completo ni el CVV.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='payment_method')
    holder = models.CharField(max_length=100)
    last4 = models.CharField(max_length=4)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.holder} (**** {self.last4})"
