import json
from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Availability, Booking, PaymentMethod, Resource


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class CreateBookingApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='qa-user',
            password='test-password',
            email='qa@example.test',
        )
        self.resource = Resource.objects.create(name='Pista QA')
        self.start = timezone.now().replace(second=0, microsecond=0) + timedelta(days=14)
        self.end = self.start + timedelta(hours=1)
        self.url = reverse('api_crear_reserva')
        self.client.force_login(self.user)

    def payload(self, **overrides):
        data = {
            'resource_id': self.resource.pk,
            'start_time': self.start.isoformat(),
            'end_time': self.end.isoformat(),
            'repeat_weeks': 0,
        }
        data.update(overrides)
        return data

    def post_booking(self, payload=None):
        return self.client.post(
            self.url,
            data=json.dumps(payload if payload is not None else self.payload()),
            content_type='application/json',
        )

    def test_authenticated_user_can_create_booking(self):
        response = self.post_booking()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        booking = Booking.objects.get()
        self.assertEqual(booking.user, self.user)
        self.assertEqual(booking.resource, self.resource)
        self.assertEqual(booking.start_time, self.start)
        self.assertEqual(booking.end_time, self.end)
        events = self.client.get(
            reverse('api_reservas', args=[self.resource.pk]),
        )
        self.assertEqual(events.status_code, 200)
        self.assertEqual(len(events.json()), 1)

    def test_anonymous_user_cannot_create_booking(self):
        self.client.logout()

        response = self.post_booking()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Booking.objects.count(), 0)

    def test_overlapping_booking_is_rejected(self):
        Booking.objects.create(
            user=self.user,
            resource=self.resource,
            start_time=self.start + timedelta(minutes=30),
            end_time=self.end + timedelta(minutes=30),
        )

        response = self.post_booking()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Booking.objects.count(), 1)

    def test_blocked_time_is_rejected_by_api(self):
        Availability.objects.create(
            resource=self.resource,
            start_time=self.start + timedelta(minutes=15),
            end_time=self.end + timedelta(minutes=15),
        )

        response = self.post_booking()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Booking.objects.count(), 0)

    def test_recurring_bookings_are_all_or_nothing_on_conflict(self):
        second_week_start = self.start + timedelta(weeks=1)
        Booking.objects.create(
            user=self.user,
            resource=self.resource,
            start_time=second_week_start,
            end_time=second_week_start + timedelta(hours=1),
        )

        response = self.post_booking(self.payload(repeat_weeks=2))

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertFalse(
            Booking.objects.filter(
                resource=self.resource,
                start_time=self.start,
            ).exists()
        )

    def test_available_recurring_bookings_are_created_for_each_week(self):
        response = self.post_booking(self.payload(repeat_weeks=2))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['reservas']), 3)
        self.assertEqual(Booking.objects.count(), 3)

    def test_recurring_booking_sends_one_confirmation_email(self):
        response = self.post_booking(self.payload(repeat_weeks=2))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Booking.objects.count(), 3)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(response.json()['correo_enviado'], True)

    def test_booking_without_user_email_does_not_send_confirmation(self):
        self.user.email = ''
        self.user.save(update_fields=['email'])

        with self.assertLogs('reservas.correos', level='WARNING'):
            response = self.post_booking()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertFalse(response.json()['correo_enviado'])
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_interval_is_rejected_without_creating_booking(self):
        response = self.post_booking(self.payload(
            end_time=self.start.isoformat(),
        ))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    def test_negative_repeat_count_is_rejected(self):
        response = self.post_booking(self.payload(repeat_weeks=-1))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    def test_repeat_count_above_maximum_is_rejected(self):
        response = self.post_booking(self.payload(repeat_weeks=13))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    def test_malformed_json_is_rejected_without_creating_booking(self):
        response = self.client.post(
            self.url,
            data='{invalid',
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    def test_non_post_request_is_rejected(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)
        self.assertEqual(Booking.objects.count(), 0)

    def test_saved_payment_method_is_used_for_quick_booking(self):
        PaymentMethod.objects.create(
            user=self.user,
            holder='QA User',
            last4='4242',
        )

        response = self.post_booking(self.payload(
            payment={'method': 'saved'},
        ))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['pagado'])
        self.assertEqual(Booking.objects.get().payment_last4, '4242')
        self.assertNotIn('number', response.json())
        self.assertEqual(len(mail.outbox), 1)

    def test_saved_payment_without_saved_method_is_rejected(self):
        response = self.post_booking(self.payload(
            payment={'method': 'saved'},
        ))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    @patch('reservas.correos.send_mail', side_effect=RuntimeError('mail unavailable'))
    def test_booking_persists_when_confirmation_email_fails(self, send_mail):
        with self.assertLogs('reservas.correos', level='ERROR'):
            response = self.post_booking()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['correo_enviado'])
        self.assertEqual(Booking.objects.count(), 1)
        send_mail.assert_called_once()

    def test_invalid_card_is_rejected_without_creating_booking(self):
        response = self.post_booking(self.payload(
            payment={
                'method': 'card',
                'card': {
                    'holder': 'QA User',
                    'number': '1234567890123456',
                    'expiry': '12/30',
                    'cvv': '123',
                },
            },
        ))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)


class AvailabilityApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='availability-user',
            password='test-password',
        )
        self.resource = Resource.objects.create(name='Availability QA')
        self.target_day = timezone.localdate() + timedelta(days=30)
        self.start = timezone.make_aware(
            datetime.combine(self.target_day, time(9)),
            timezone.get_current_timezone(),
        )
        self.url = reverse('api_disponibilidad', args=[self.resource.pk])

    def get_day(self, day=None):
        day = day or self.target_day
        return self.client.get(
            self.url,
            {'start': day.isoformat(), 'end': day.isoformat()},
        )

    def test_availability_reports_partial_day_for_one_booking(self):
        Booking.objects.create(
            user=self.user,
            resource=self.resource,
            start_time=self.start,
            end_time=self.start + timedelta(hours=1),
        )

        response = self.get_day()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['dias'][0]['estado'], 'parcial')
        self.assertEqual(response.json()['dias'][0]['libres'], 11)

    def test_availability_reports_occupied_day_for_full_day_block(self):
        Availability.objects.create(
            resource=self.resource,
            start_time=self.start,
            end_time=self.start + timedelta(hours=12),
        )

        response = self.get_day()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['dias'][0]['estado'], 'ocupado')
        self.assertEqual(response.json()['dias'][0]['libres'], 0)

    def test_availability_rejects_invalid_date_range(self):
        response = self.client.get(
            self.url,
            {
                'start': self.target_day.isoformat(),
                'end': (self.target_day - timedelta(days=1)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 400)


class DemandForecastTests(TestCase):
    def setUp(self):
        self.resource = Resource.objects.create(
            name='Demand QA',
            price_per_hour='20.00',
        )
        self.url = reverse('api_demanda', args=[self.resource.pk])
        self.user = get_user_model().objects.create_user(
            username='demand-user',
            password='test-password',
        )

    def test_demand_api_rejects_non_staff_user(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_staff_can_read_forecast_data(self):
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['historico']), 12)
        self.assertEqual(len(response.json()['prevision']), 4)
        self.assertIn('sugerencia', response.json())
        self.assertEqual(response.json()['prevision'], [0, 0, 0, 0])

    def test_demand_panel_renders_for_staff_and_redirects_anonymous_user(self):
        panel_url = reverse('panel_demanda')
        response = self.client.get(panel_url)
        self.assertEqual(response.status_code, 302)

        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        self.client.force_login(self.user)
        response = self.client.get(panel_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Gráficos por recurso')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class MyBookingsAndConfirmationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='booking-owner',
            password='test-password',
            email='owner@example.test',
        )
        self.other_user = get_user_model().objects.create_user(
            username='other-owner',
            password='test-password',
            email='other@example.test',
        )
        self.resource = Resource.objects.create(name='My bookings QA')
        self.start = timezone.now() + timedelta(days=20)
        self.booking = Booking.objects.create(
            user=self.user,
            resource=self.resource,
            start_time=self.start,
            end_time=self.start + timedelta(hours=1),
        )
        self.client.force_login(self.user)

    def test_user_can_view_own_upcoming_booking(self):
        response = self.client.get(reverse('mis_reservas'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.resource.name)
        self.assertContains(response, 'Próximas reservas')

    def test_user_cannot_cancel_another_users_booking(self):
        self.booking.user = self.other_user
        self.booking.save(update_fields=['user'])

        response = self.client.post(
            reverse('cancelar_reserva', args=[self.booking.pk]),
        )

        self.assertEqual(response.status_code, 403)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.CONFIRMADA)

    def test_owner_can_cancel_upcoming_booking(self):
        response = self.client.post(
            reverse('cancelar_reserva', args=[self.booking.pk]),
        )

        self.assertEqual(response.status_code, 302)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.CANCELADA)
        self.assertIsNotNone(self.booking.cancelled_at)

    def test_owner_cannot_cancel_booking_that_already_started(self):
        self.booking.start_time = timezone.now() - timedelta(hours=2)
        self.booking.end_time = timezone.now() - timedelta(hours=1)
        self.booking.save(update_fields=['start_time', 'end_time'])

        response = self.client.post(
            reverse('cancelar_reserva', args=[self.booking.pk]),
        )

        self.assertEqual(response.status_code, 302)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.CONFIRMADA)
        self.assertIsNone(self.booking.cancelled_at)

    def test_owner_cannot_cancel_booking_twice(self):
        self.booking.status = Booking.CANCELADA
        self.booking.cancelled_at = timezone.now() - timedelta(minutes=5)
        original_cancelled_at = self.booking.cancelled_at
        self.booking.save(update_fields=['status', 'cancelled_at'])

        response = self.client.post(
            reverse('cancelar_reserva', args=[self.booking.pk]),
        )

        self.assertEqual(response.status_code, 302)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.CANCELADA)
        self.assertEqual(self.booking.cancelled_at, original_cancelled_at)

    def test_cancelled_booking_frees_slot_for_a_new_booking(self):
        self.client.post(reverse('cancelar_reserva', args=[self.booking.pk]))
        response = self.client.post(
            reverse('api_crear_reserva'),
            data=json.dumps({
                'resource_id': self.resource.pk,
                'start_time': self.start.isoformat(),
                'end_time': (self.start + timedelta(hours=1)).isoformat(),
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Booking.objects.count(), 2)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.CANCELADA)

    def test_booking_confirmation_email_contains_booking_summary(self):
        from .correos import enviar_confirmacion

        sent = enviar_confirmacion(
            self.user,
            self.resource,
            [(self.start, self.start + timedelta(hours=1))],
            self.resource.price_per_hour,
        )

        self.assertTrue(sent)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.resource.name, mail.outbox[0].body)
        self.assertIn('Total:', mail.outbox[0].body)


class PaymentMethodPageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='payment-user',
            password='test-password',
        )
        self.client.force_login(self.user)
        self.url = reverse('mis_pagos')

    def test_user_can_save_only_card_holder_and_last_four_digits(self):
        response = self.client.post(self.url, {
            'holder': 'QA Cardholder',
            'number': '4242 4242 4242 4242',
            'expiry': '12/30',
            'cvv': '123',
        })

        self.assertEqual(response.status_code, 302)
        saved = PaymentMethod.objects.get(user=self.user)
        self.assertEqual(saved.holder, 'QA Cardholder')
        self.assertEqual(saved.last4, '4242')
        self.assertNotIn('number', [field.name for field in saved._meta.fields])
        self.assertNotIn('cvv', [field.name for field in saved._meta.fields])

    def test_invalid_card_is_not_saved(self):
        response = self.client.post(self.url, {
            'holder': 'QA Cardholder',
            'number': '1234567890123456',
            'expiry': '12/30',
            'cvv': '123',
        })

        self.assertEqual(response.status_code, 302)
        self.assertFalse(PaymentMethod.objects.filter(user=self.user).exists())

    def test_user_can_delete_saved_payment_method(self):
        PaymentMethod.objects.create(
            user=self.user,
            holder='QA Cardholder',
            last4='4242',
        )

        response = self.client.post(self.url, {'accion': 'eliminar'})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(PaymentMethod.objects.filter(user=self.user).exists())


class DemandForecastCalculationTests(TestCase):
    def test_moving_average_projects_from_previous_forecast(self):
        from .demanda import media_movil

        self.assertEqual(media_movil([3, 6, 9], semanas_futuras=2), [6.0, 7.0])

    def test_price_suggestion_uses_high_occupancy_threshold_inclusively(self):
        from decimal import Decimal

        from .demanda import sugerencia_precio

        result = sugerencia_precio(Decimal('20.00'), 0.50)

        self.assertEqual(result['accion'], 'subir')
        self.assertEqual(result['precio_sugerido'], '22.00')

    def test_price_suggestion_uses_low_occupancy_threshold_inclusively(self):
        from decimal import Decimal

        from .demanda import sugerencia_precio

        result = sugerencia_precio(Decimal('20.00'), 0.15)

        self.assertEqual(result['accion'], 'bajar')
        self.assertEqual(result['precio_sugerido'], '18.00')
