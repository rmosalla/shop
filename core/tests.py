from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import Party, StoreSettings


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
