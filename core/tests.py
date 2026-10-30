from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import Party, Period, StoreSettings

User = get_user_model()


class PartyTests(TestCase):
    def test_str_returns_name(self):
        p = Party.objects.create(name="علی")
        self.assertEqual(str(p), "علی")

    def test_roles_default_to_false(self):
        p = Party.objects.create(name="x")
        self.assertFalse(p.is_supplier or p.is_customer or p.is_partner or p.is_seller)


class StoreSettingsTests(TestCase):
    def test_defaults_are_set(self):
        s = StoreSettings.objects.create(store_name="Test Store")
        self.assertEqual(s.base_currency, "IRT")
        self.assertEqual(s.profit_mode, "base")
        self.assertEqual(s.costing_method, "wavg")

    def test_str_returns_name(self):
        s = StoreSettings.objects.create(store_name="Test Store")
        self.assertEqual(str(s), "Test Store")

    def test_enabled_modules_is_empty(self):
        s = StoreSettings.objects.create(store_name="Test Store")
        self.assertEqual(s.enabled_modules, [])

    def test_second_instance_is_rejected(self):
        StoreSettings.objects.create(store_name="Test Store1")
        with self.assertRaises(ValidationError):
            StoreSettings.objects.create(store_name="Test Store2")
        self.assertEqual(StoreSettings.objects.count(), 1)

    def test_changing_store_name_does_not_raise(self):
        s = StoreSettings.objects.create(store_name="Test Store")
        s.store_name = "Changed Name"
        s.save()
        s.refresh_from_db()
        self.assertEqual(s.store_name, "Changed Name")

    def test_clean_rejects_second_instance(self):
        StoreSettings.objects.create(store_name="Test Store")
        second = StoreSettings(store_name="Test Store2")
        with self.assertRaises(ValidationError):
            second.full_clean()

    def test_clean_allows_existing_instance(self):
        s = StoreSettings.objects.create(store_name="Test Store")
        s.full_clean()

    def test_has_module_true_when_enabled(self):
        s = StoreSettings.objects.create(
            store_name="Test Store",
            enabled_modules=["currency"],
        )
        self.assertTrue(s.has_module("currency"))

    def test_has_module_false_when_not_enabled(self):
        s = StoreSettings.objects.create(
            store_name="Test Store",
            enabled_modules=["currency"],
        )
        self.assertFalse(s.has_module("installments"))

    def test_has_module_false_when_empty(self):
        s = StoreSettings.objects.create(
            store_name="Test Store",
        )
        self.assertFalse(s.has_module("installments"))

    def test_get_solo_creates_settings_when_missing(self):
        self.assertEqual(StoreSettings.objects.count(), 0)
        StoreSettings.get_solo()
        self.assertEqual(StoreSettings.objects.count(), 1)

    def test_get_solo_returns_existing_settings(self):
        existing = StoreSettings.objects.create(store_name="Test Store")
        found = StoreSettings.get_solo()
        self.assertEqual(found.pk, existing.pk)
        self.assertEqual(StoreSettings.objects.count(), 1)


class PeriodTests(TestCase):
    def test_reject_reversed_dates(self):
        p = Period(
            name="october", start_date=date(2026, 10, 30), end_date=date(2026, 10, 1)
        )
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_valid_period_is_accepted(self):
        p = Period(
            name="october", start_date=date(2026, 10, 1), end_date=date(2026, 10, 30)
        )
        p.full_clean()

    def test_add_one_day_period_accepted(self):
        p = Period(
            name="one day", start_date=date(2026, 10, 1), end_date=date(2026, 10, 1)
        )
        p.full_clean()

    def test_reject_date_in_closed_period(self):
        Period.objects.create(
            name="october",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 30),
            status=Period.Status.CLOSED,
        )
        with self.assertRaises(ValidationError):
            Period.assert_date_open(date(2026, 10, 5))

    def test_date_in_open_period_accepted(self):
        Period.objects.create(
            name="october",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 30),
        )
        Period.assert_date_open(date(2026, 10, 5))

    def test_date_with_no_periods_is_accepted(self):
        Period.assert_date_open(date(2026, 10, 5))

    def test_date_equal_to_closed_period_start_date_rejected(self):
        Period.objects.create(
            name="october",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 30),
            status=Period.Status.CLOSED,
        )
        with self.assertRaises(ValidationError):
            Period.assert_date_open(date(2026, 10, 1))

    def test_date_equal_to_closed_period_end_date_rejected(self):
        Period.objects.create(
            name="october",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 30),
            status=Period.Status.CLOSED,
        )
        with self.assertRaises(ValidationError):
            Period.assert_date_open(date(2026, 10, 30))

    def test_date_out_of_closed_period_accepted(self):
        Period.objects.create(
            name="october",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 30),
            status=Period.Status.CLOSED,
        )
        Period.assert_date_open(date(2026, 11, 1))

    def test_add_period_without_startdate_or_enddate_reject(self):
        p = Period(name="No date")
        with self.assertRaises(ValidationError):
            p.full_clean()


class PeriodCloseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="admin", password="pass12345")
        self.period = Period.objects.create(
            name="october",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 30),
        )

    def test_close_sets_status_closed(self):
        self.assertEqual(self.period.status, Period.Status.OPEN)
        self.period.close(self.user)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, Period.Status.CLOSED)

    def test_close_period_closed_by_logined_user(self):
        self.period.close(self.user)
        self.period.refresh_from_db()
        self.assertEqual(self.period.closed_by, self.user)

    def test_close_period_closed_at_not_none(self):
        self.period.close(self.user)
        self.period.refresh_from_db()
        self.assertIsNotNone(self.period.closed_at)

    def test_close_closed_period_rejected(self):
        self.period.close(self.user)
        with self.assertRaises(ValidationError):
            self.period.close(self.user)

    def test_edit_closed_period_rejected(self):
        self.period.close(self.user)
        self.period.end_date = date(2026, 10, 15)
        with self.assertRaises(ValidationError):
            self.period.save()

    def test_edit_open_period_accepted(self):
        self.period.end_date = date(2026, 10, 15)
        self.period.save()
        self.period.refresh_from_db()
        self.assertEqual(self.period.end_date, date(2026, 10, 15))

    def test_clean_edit_closed_period_rejected(self):
        self.period.close(self.user)
        with self.assertRaises(ValidationError):
            self.period.full_clean()

    def test_delete_closed_period_rejected(self):
        self.period.close(self.user)
        with self.assertRaises(ValidationError):
            self.period.delete()
        self.assertEqual(Period.objects.count(), 1)

    def test_delete_open_period_accepted(self):
        self.period.delete()
        self.assertEqual(Period.objects.count(), 0)
