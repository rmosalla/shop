from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import TestCase

from core.models import Party, Period

from .models import Purchase


class PurchaseTests(TestCase):
    def setUp(self):
        self.supplier = Party.objects.create(name="Supplier A", is_supplier=True)
        self.customer = Party.objects.create(name="Customer B", is_customer=True)

    def make(self, **overrides):
        data = {"supplier": self.supplier, "date": date(2026, 10, 5)}
        data.update(overrides)
        return Purchase(**data)

    def test_defaults(self):
        p = Purchase.objects.create(supplier=self.supplier, date=date(2026, 10, 5))
        self.assertEqual(p.currency, "IRT")
        self.assertEqual(p.exchange_rate, Decimal("1"))
        self.assertEqual(p.status, Purchase.Status.DRAFT)
        self.assertEqual(p.invoice_no, "")

    def test_str(self):
        p = Purchase.objects.create(supplier=self.supplier, date=date(2026, 10, 5))
        self.assertEqual(str(p), "Supplier A - 2026-10-05")

    def test_valid_purchase_accepted(self):
        self.make().full_clean()

    def test_party_without_supplier_role_rejected(self):
        with self.assertRaises(ValidationError):
            self.make(supplier=self.customer).full_clean()

    def test_non_positive_exchange_rate_rejected(self):
        for rate in [Decimal("0"), Decimal("-1")]:
            with self.subTest(rate=rate):
                with self.assertRaises(ValidationError):
                    self.make(exchange_rate=rate).full_clean()

    def test_foreign_currency_rate_accepted(self):
        self.make(currency="IQD", exchange_rate=Decimal("0.0345")).full_clean()

    def test_invalid_status_rejected(self):
        with self.assertRaises(ValidationError):
            self.make(status="bogus").full_clean()

    def test_date_in_closed_period_rejected(self):
        Period.objects.create(
            name="october",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 30),
            status=Period.Status.CLOSED,
        )
        with self.assertRaises(ValidationError):
            self.make().full_clean()

    def test_date_in_open_period_accepted(self):
        Period.objects.create(
            name="october",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 30),
        )
        self.make().full_clean()

    def test_purchases_reachable_from_supplier(self):
        p = Purchase.objects.create(supplier=self.supplier, date=date(2026, 10, 5))
        self.assertEqual(list(self.supplier.purchases.all()), [p])

    def test_cannot_delete_supplier_with_purchases(self):
        Purchase.objects.create(supplier=self.supplier, date=date(2026, 10, 5))
        with self.assertRaises(ProtectedError):
            self.supplier.delete()

    def test_missing_date_rejected_without_crashing(self):
        p = Purchase(supplier=self.supplier)
        with self.assertRaises(ValidationError):
            p.full_clean()
