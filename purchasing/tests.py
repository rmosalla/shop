from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import TestCase

from catalog.models import AttributeDefinition, Category, Product, Variant
from core.models import Party, Period

from .models import Purchase, PurchaseLine


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

    def test_rate_with_four_decimals_accepted(self):
        self.make(currency="IQD", exchange_rate=Decimal("0.0001")).full_clean()

    def test_rate_with_five_decimals_rejected(self):
        with self.assertRaises(ValidationError):
            self.make(currency="IQD", exchange_rate=Decimal("0.00001")).full_clean()


class PurchaseLineTests(TestCase):
    def setUp(self):
        supplier = Party.objects.create(name="Supplier A", is_supplier=True)
        category = Category.objects.create(name="Laptop")
        product = Product.objects.create(
            category=category, brand="Dell", model_name="Latitude 5420"
        )
        self.variant = Variant.objects.create(product=product, sku="DELL-5420-A")
        self.purchase = Purchase.objects.create(
            supplier=supplier, date=date(2026, 10, 5)
        )
        self.fx_purchase = Purchase.objects.create(
            supplier=supplier,
            date=date(2026, 10, 6),
            currency="AED",
            exchange_rate=Decimal("2.5"),
        )

    def make(self, **overrides):
        data = {
            "purchase": self.purchase,
            "variant": self.variant,
            "qty": 2,
            "unit_price": Decimal("1500000"),
        }
        data.update(overrides)
        return PurchaseLine(**data)

    def test_valid_line_accepted(self):
        self.make().full_clean()

    def test_default_qty_is_one(self):
        line = PurchaseLine.objects.create(
            purchase=self.purchase, variant=self.variant, unit_price=Decimal("10")
        )
        self.assertEqual(line.qty, 1)

    def test_str(self):
        self.assertEqual(str(self.make()), f"{self.variant.sku} x 2")

    def test_zero_or_negative_qty_rejected(self):
        for qty in [0, -1]:
            with self.subTest(qty=qty):
                with self.assertRaises(ValidationError):
                    self.make(qty=qty).full_clean()

    def test_negative_price_rejected(self):
        with self.assertRaises(ValidationError):
            self.make(unit_price=Decimal("-1")).full_clean()

    def test_zero_price_accepted(self):
        self.make(unit_price=Decimal("0")).full_clean()

    def test_price_with_three_decimals_rejected(self):
        with self.assertRaises(ValidationError):
            self.make(unit_price=Decimal("10.001")).full_clean()

    def test_line_without_purchase_or_variant_rejected(self):
        for missing in ["purchase", "variant"]:
            with self.subTest(missing=missing):
                line = self.make()
                setattr(line, missing, None)
                with self.assertRaises(ValidationError):
                    line.full_clean()

    def test_line_total(self):
        self.assertEqual(self.make().total, Decimal("3000000"))

    def test_line_total_base_with_rate_one(self):
        self.assertEqual(self.make().total_base, Decimal("3000000"))

    def test_line_total_base_with_exchange_rate(self):
        line = self.make(purchase=self.fx_purchase, qty=3, unit_price=Decimal("10.10"))
        self.assertEqual(line.total, Decimal("30.30"))
        self.assertEqual(line.total_base, Decimal("75.75"))

    def test_line_total_base_rounds_half_up(self):
        purchase = Purchase.objects.create(
            supplier=self.purchase.supplier,
            date=date(2026, 10, 7),
            currency="AED",
            exchange_rate=Decimal("0.5"),
        )
        line = self.make(purchase=purchase, qty=1, unit_price=Decimal("0.01"))
        self.assertEqual(line.total_base, Decimal("0.01"))

    def test_same_variant_twice_in_one_purchase_allowed(self):
        PurchaseLine.objects.create(
            purchase=self.purchase, variant=self.variant, unit_price=Decimal("10")
        )
        second = self.make(unit_price=Decimal("11"))
        second.full_clean()

    def test_lines_reachable_from_purchase(self):
        line = self.make()
        line.save()
        self.assertEqual(list(self.purchase.lines.all()), [line])

    def test_cannot_delete_variant_with_purchase_lines(self):
        self.make().save()
        with self.assertRaises(ProtectedError):
            self.variant.delete()

    def test_deleting_purchase_deletes_its_lines(self):
        self.make().save()
        self.purchase.delete()
        self.assertEqual(PurchaseLine.objects.count(), 0)


class PurchaseTotalsTests(TestCase):
    def setUp(self):
        supplier = Party.objects.create(name="Supplier A", is_supplier=True)
        category = Category.objects.create(name="Laptop")
        product = Product.objects.create(category=category, model_name="x")
        self.variant = Variant.objects.create(product=product, sku="A")
        self.purchase = Purchase.objects.create(
            supplier=supplier,
            date=date(2026, 10, 5),
            currency="AED",
            exchange_rate=Decimal("2.5"),
        )

    def test_empty_purchase_totals_are_zero(self):
        self.assertEqual(self.purchase.total, Decimal("0"))
        self.assertEqual(self.purchase.total_base, Decimal("0"))

    def test_purchase_totals_sum_lines(self):
        PurchaseLine.objects.create(
            purchase=self.purchase,
            variant=self.variant,
            qty=2,
            unit_price=Decimal("10.00"),
        )
        PurchaseLine.objects.create(
            purchase=self.purchase,
            variant=self.variant,
            qty=1,
            unit_price=Decimal("5.50"),
        )
        self.assertEqual(self.purchase.total, Decimal("25.50"))
        self.assertEqual(self.purchase.total_base, Decimal("63.75"))


class VariantLockedByDocumentsTests(TestCase):
    def setUp(self):
        supplier = Party.objects.create(name="Supplier A", is_supplier=True)
        category = Category.objects.create(name="Laptop")
        self.product = Product.objects.create(
            category=category, brand="Dell", model_name="Latitude 5420"
        )
        self.other_product = Product.objects.create(
            category=category, brand="HP", model_name="EliteBook"
        )
        AttributeDefinition.objects.create(
            key="ram", label="رم", value_type=AttributeDefinition.ValueType.NUMBER
        )
        self.variant = Variant.objects.create(
            product=self.product, attributes={"ram": 16}
        )
        self.purchase = Purchase.objects.create(
            supplier=supplier, date=date(2026, 10, 5)
        )

    def use_variant(self):
        PurchaseLine.objects.create(
            purchase=self.purchase, variant=self.variant, unit_price=Decimal("10")
        )

    def test_unused_variant_has_no_documents(self):
        self.assertFalse(self.variant.has_documents())

    def test_variant_with_purchase_line_has_documents(self):
        self.use_variant()
        self.assertTrue(self.variant.has_documents())

    def test_unused_variant_can_change_and_sku_follows(self):
        self.variant.attributes = {"ram": 32}
        self.variant.save()
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.sku, "DELL-LATITUDE-5420-32")

    def test_used_variant_attributes_cannot_change_on_save(self):
        self.use_variant()
        self.variant.attributes = {"ram": 32}
        with self.assertRaises(ValidationError):
            self.variant.save()

    def test_used_variant_attributes_cannot_change_in_clean(self):
        self.use_variant()
        self.variant.attributes = {"ram": 32}
        with self.assertRaises(ValidationError):
            self.variant.full_clean()

    def test_used_variant_product_cannot_change(self):
        self.use_variant()
        self.variant.product = self.other_product
        with self.assertRaises(ValidationError):
            self.variant.save()

    def test_used_variant_sku_ignores_in_memory_change(self):
        self.use_variant()
        old_sku = self.variant.sku
        self.variant.sku = "HACK"
        self.variant.save()
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.sku, old_sku)

    def test_used_variant_price_can_change(self):
        self.use_variant()
        self.variant.default_price_base = Decimal("2000000")
        self.variant.save()
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.default_price_base, Decimal("2000000"))

    def test_used_variant_unchanged_passes_full_clean(self):
        self.use_variant()
        self.variant.full_clean()
