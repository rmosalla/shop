from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import TestCase

from catalog.models import Category, Product, Variant
from core.models import Party
from purchasing.models import Purchase, PurchaseLine

from .models import Unit


class UnitTests(TestCase):
    def setUp(self):
        supplier = Party.objects.create(name="Supplier A", is_supplier=True)
        category = Category.objects.create(name="Laptop")
        product = Product.objects.create(
            category=category, brand="Dell", model_name="Latitude 5420"
        )
        self.variant = Variant.objects.create(product=product)
        self.purchase = Purchase.objects.create(
            supplier=supplier, date=date(2026, 10, 5)
        )
        self.line = PurchaseLine.objects.create(
            purchase=self.purchase,
            variant=self.variant,
            qty=2,
            unit_price=Decimal("1500000"),
        )

    def make(self, **overrides):
        data = {
            "variant": self.variant,
            "purchase_line": self.line,
            "cost_amount": Decimal("1500000"),
            "cost_currency": "IRT",
            "cost_rate": Decimal("1"),
            "cost_base": Decimal("1500000"),
            "in_stock_since": date(2026, 10, 5),
        }
        data.update(overrides)
        return Unit(**data)

    def create(self, **overrides):
        unit = self.make(**overrides)
        unit.save()
        return unit

    def test_valid_unit_accepted(self):
        self.make().full_clean()

    def test_defaults(self):
        unit = self.create()
        self.assertEqual(unit.status, Unit.Status.IN_STOCK)
        self.assertEqual(unit.condition, Unit.Condition.NEW)
        self.assertEqual(unit.serial_number, "")
        self.assertEqual(unit.grade, "")
        self.assertIsNone(unit.battery_health)
        self.assertIsNone(unit.asking_price_base)

    def test_uid_is_generated_from_pk(self):
        unit = self.create()
        self.assertEqual(unit.uid, f"U{unit.pk:06d}")
        unit.refresh_from_db()
        self.assertEqual(unit.uid, f"U{unit.pk:06d}")

    def test_uids_are_unique(self):
        first = self.create()
        second = self.create()
        self.assertNotEqual(first.uid, second.uid)

    def test_uid_is_not_editable(self):
        self.assertFalse(Unit._meta.get_field("uid").editable)

    def test_uid_stays_after_resave(self):
        unit = self.create()
        old_uid = unit.uid
        unit.note = "changed"
        unit.save()
        unit.refresh_from_db()
        self.assertEqual(unit.uid, old_uid)

    def test_uid_cannot_be_changed_in_memory(self):
        unit = self.create()
        old_uid = unit.uid
        unit.uid = "HACK"
        unit.save()
        unit.refresh_from_db()
        self.assertEqual(unit.uid, old_uid)

    def test_str_returns_uid(self):
        unit = self.create()
        self.assertEqual(str(unit), unit.uid)

    def test_str_of_unsaved_unit(self):
        self.assertEqual(str(self.make()), "دستگاه جدید")

    def test_blank_serial_allowed(self):
        self.make(serial_number="").full_clean()

    def test_duplicate_serial_allowed(self):
        self.create(serial_number="SN-1")
        self.make(serial_number="SN-1").full_clean()

    def test_battery_health_range(self):
        for value in [0, 85, 100]:
            with self.subTest(value=value):
                self.make(battery_health=value).full_clean()
        for value in [101, -1]:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    self.make(battery_health=value).full_clean()

    def test_negative_costs_rejected(self):
        for field in ["cost_amount", "cost_base"]:
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    self.make(**{field: Decimal("-1")}).full_clean()

    def test_zero_cost_accepted(self):
        self.make(cost_amount=Decimal("0"), cost_base=Decimal("0")).full_clean()

    def test_cost_with_three_decimals_rejected(self):
        with self.assertRaises(ValidationError):
            self.make(cost_amount=Decimal("10.001")).full_clean()

    def test_zero_cost_rate_rejected(self):
        with self.assertRaises(ValidationError):
            self.make(cost_rate=Decimal("0")).full_clean()

    def test_missing_required_fields_rejected(self):
        for field in ["variant", "purchase_line", "in_stock_since", "cost_currency"]:
            with self.subTest(field=field):
                unit = self.make()
                setattr(unit, field, None if field != "cost_currency" else "")
                with self.assertRaises(ValidationError):
                    unit.full_clean()

    def test_invalid_choices_rejected(self):
        for field, value in [
            ("status", "bogus"),
            ("condition", "bogus"),
            ("grade", "Z"),
        ]:
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    self.make(**{field: value}).full_clean()

    def test_valid_grade_accepted(self):
        self.make(condition=Unit.Condition.USED, grade="B").full_clean()

    def test_variant_must_match_purchase_line(self):
        other_product = Product.objects.create(
            category=self.variant.product.category, model_name="Other"
        )
        other = Variant.objects.create(product=other_product)
        with self.assertRaises(ValidationError):
            self.make(variant=other).full_clean()

    def test_quantity_tracked_product_rejected(self):
        product = Product.objects.create(
            category=self.variant.product.category,
            model_name="Mouse",
            tracking_type=Product.Tracking.QUANTITY,
        )
        variant = Variant.objects.create(product=product)
        line = PurchaseLine.objects.create(
            purchase=self.purchase, variant=variant, unit_price=Decimal("10")
        )
        with self.assertRaises(ValidationError):
            self.make(variant=variant, purchase_line=line).full_clean()

    def test_effective_price_uses_asking_price_when_set(self):
        Variant.objects.filter(pk=self.variant.pk).update(
            default_price_base=Decimal("2000000")
        )
        self.variant.refresh_from_db()
        unit = self.create(asking_price_base=Decimal("1800000"))
        self.assertEqual(unit.effective_price_base, Decimal("1800000"))

    def test_effective_price_falls_back_to_variant_price(self):
        Variant.objects.filter(pk=self.variant.pk).update(
            default_price_base=Decimal("2000000")
        )
        unit = self.create()
        unit.refresh_from_db()
        self.assertEqual(unit.effective_price_base, Decimal("2000000"))

    def test_zero_asking_price_is_respected(self):
        unit = self.create(asking_price_base=Decimal("0"))
        self.assertEqual(unit.effective_price_base, Decimal("0"))

    def test_units_reachable_from_purchase_line(self):
        unit = self.create()
        self.assertEqual(list(self.line.units.all()), [unit])

    def test_cannot_delete_purchase_line_with_units(self):
        self.create()
        with self.assertRaises(ProtectedError):
            self.line.delete()

    def test_variant_with_units_counts_as_used(self):
        self.create()
        self.assertTrue(self.variant.has_documents())
