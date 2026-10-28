import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Availability, Booking, Resource


class CreateBookingApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='qa-user',
            password='test-password'
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
