import random
from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from reservas.demanda import lunes_de
from reservas.disponibilidad import HORA_FIN, HORA_INICIO
from reservas.models import Booking, Resource

# (reservas base por día, crecimiento durante el periodo) para cada recurso, en orden de id
PERFILES = [(5.0, 0.0), (3.0, 0.1), (2.5, 0.6), (1.0, 0.0)]

# Peso de cada día de la semana, de lunes a domingo (fines de semana con más demanda)
PESO_DIA = [0.6, 0.6, 0.7, 0.8, 1.0, 1.4, 1.3]


class Command(BaseCommand):
    help = "Crea reservas pasadas de prueba para ver los gráficos de demanda"

    def add_arguments(self, parser):
        parser.add_argument('--semanas', type=int, default=12, help='Semanas de historial a crear')

    def handle(self, *args, **options):
        semanas = options['semanas']
        azar = random.Random(2026)  # semilla fija para que siempre salgan los mismos datos
        zona = timezone.get_current_timezone()

        usuario, _ = User.objects.get_or_create(username='historial_demo')
        usuario.set_unusable_password()
        usuario.save()
        # Solo se borran las reservas que creó este mismo comando
        Booking.objects.filter(user=usuario).delete()

        lunes_actual = lunes_de(timezone.localdate())
        horas = list(range(HORA_INICIO, HORA_FIN))
        # Las horas de la tarde se reservan más
        peso_hora = {h: (3 if h >= 17 else 1) for h in horas}
        creadas = 0

        for posicion, recurso in enumerate(Resource.objects.order_by('id')):
            base, crecimiento = PERFILES[posicion % len(PERFILES)]
            for semana in range(semanas):
                lunes = lunes_actual - timedelta(weeks=semanas - semana)
                factor = 1 + crecimiento * semana
                for i in range(7):
                    dia = lunes + timedelta(days=i)
                    cantidad = round(base * factor * PESO_DIA[i]) + azar.choice([-1, 0, 1])
                    cantidad = max(0, min(cantidad, len(horas)))
                    # Elige horas distintas dando más probabilidad a las de mayor peso
                    ordenadas = sorted(horas, key=lambda h: azar.random() ** (1 / peso_hora[h]))
                    elegidas = ordenadas[len(horas) - cantidad:]
                    for hora in elegidas:
                        inicio = timezone.make_aware(datetime.combine(dia, time(hora)), zona)
                        fin = inicio + timedelta(hours=1)
                        if Booking.objects.activas().filter(resource=recurso, start_time__lt=fin, end_time__gt=inicio).exists():
                            continue
                        Booking.objects.create(
                            user=usuario, resource=recurso, start_time=inicio, end_time=fin,
                            price=recurso.price_per_hour, paid=True, payment_last4='4242',
                        )
                        creadas += 1

        self.stdout.write(self.style.SUCCESS(f"Se crearon {creadas} reservas de historial."))
