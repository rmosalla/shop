from django.test import TestCase

from .models import Party


class PartyTests(TestCase):
    def test_str_returns_name(self):
        p = Party.objects.create(name="علی")
        self.assertEqual(str(p), "علی")

    def test_roles_default_to_false(self):
        p = Party.objects.create(name="x")
        self.assertFalse(p.is_supplier or p.is_customer or p.is_partner or p.is_seller)
