from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import TestCase

from catalog.models import AttributeDefinition, Category, Product, Variant
from core.models import Currency, Party, Period, StoreSettings

from .models import Purchase, PurchaseLine, PurchaseLineOwnership


def create_currencies():
    Currency.objects.create(code="IRT", name="تومان", decimal_places=0)
    Currency.objects.create(code="USD", name="دلار")
    Currency.objects.create(code="AED", name="درهم")
    Currency.objects.create(code="IQD", name="دینار عراق")


class PurchaseTests(TestCase):
    def setUp(self):
        create_currencies()
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

    def test_unknown_currency_rejected(self):
        with self.assertRaises(ValidationError):
            self.make(currency="XYZ").full_clean()

    def test_inactive_currency_rejected(self):
        Currency.objects.filter(code="USD").update(is_active=False)
        with self.assertRaises(ValidationError):
            self.make(currency="USD", exchange_rate=Decimal("100000")).full_clean()

    def test_lowercase_currency_accepted(self):
        self.make(currency="usd", exchange_rate=Decimal("100000")).full_clean()

    def test_blank_currency_rejected(self):
        with self.assertRaises(ValidationError):
            self.make(currency="").full_clean()


class PurchaseLineTests(TestCase):
    def setUp(self):
        create_currencies()
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
        self.assertEqual(line.total_base, Decimal("76"))

    def test_line_total_base_rounds_half_up_to_base_decimals(self):
        purchase = Purchase.objects.create(
            supplier=self.purchase.supplier,
            date=date(2026, 10, 7),
            currency="AED",
            exchange_rate=Decimal("0.5"),
        )
        line = self.make(purchase=purchase, qty=1, unit_price=Decimal("3.00"))
        self.assertEqual(line.total_base, Decimal("2"))
        self.assertEqual(line.total_base.as_tuple().exponent, 0)

    def test_line_total_base_follows_base_currency_decimals(self):
        Currency.objects.create(code="TST", name="تست", decimal_places=1)
        StoreSettings.objects.create(store_name="S", base_currency="TST")
        purchase = Purchase.objects.create(
            supplier=self.purchase.supplier,
            date=date(2026, 10, 7),
            currency="AED",
            exchange_rate=Decimal("0.5"),
        )
        line = self.make(purchase=purchase, qty=1, unit_price=Decimal("0.30"))
        self.assertEqual(line.total_base, Decimal("0.2"))

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

    def test_zero_decimal_currency_rejects_fractional_price(self):
        with self.assertRaises(ValidationError):
            self.make(unit_price=Decimal("1500000.50")).full_clean()

    def test_zero_decimal_currency_accepts_whole_price_with_trailing_zeros(self):
        self.make(unit_price=Decimal("1500000.00")).full_clean()

    def test_two_decimal_currency_accepts_two_decimals(self):
        self.make(purchase=self.fx_purchase, unit_price=Decimal("10.55")).full_clean()

    def test_unknown_purchase_currency_is_left_to_the_purchase_validation(self):
        purchase = Purchase.objects.create(
            supplier=self.purchase.supplier,
            date=date(2026, 10, 8),
            currency="XYZ",
        )
        self.make(purchase=purchase).full_clean()


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

    def test_purchase_total_base_sums_rounded_lines(self):
        create_currencies()
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
        self.assertEqual(self.purchase.total_base, Decimal("64"))


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


class CurrencyLockWithPurchasesTests(TestCase):
    def setUp(self):
        create_currencies()
        self.supplier = Party.objects.create(name="Supplier A", is_supplier=True)

    def buy(self, currency, rate):
        return Purchase.objects.create(
            supplier=self.supplier,
            date=date(2026, 10, 5),
            currency=currency,
            exchange_rate=rate,
        )

    def test_currency_used_by_purchase_is_in_use(self):
        self.buy("USD", Decimal("100000"))
        self.assertTrue(Currency.objects.get(code="USD").is_in_use())

    def test_unused_foreign_currency_is_not_in_use(self):
        self.buy("USD", Decimal("100000"))
        self.assertFalse(Currency.objects.get(code="AED").is_in_use())

    def test_used_currency_decimals_are_locked(self):
        self.buy("USD", Decimal("100000"))
        usd = Currency.objects.get(code="USD")
        usd.decimal_places = 0
        with self.assertRaises(ValidationError):
            usd.save()

    def test_base_currency_in_use_after_any_purchase(self):
        self.buy("USD", Decimal("100000"))
        self.assertTrue(Currency.objects.get(code="IRT").is_in_use())

    def test_base_currency_not_in_use_without_purchases(self):
        self.assertFalse(Currency.objects.get(code="IRT").is_in_use())

    def test_base_currency_setting_locked_after_first_purchase(self):
        store = StoreSettings.objects.create(store_name="S")
        self.buy("IRT", Decimal("1"))
        store.base_currency = "USD"
        with self.assertRaises(ValidationError):
            store.save()

    def test_base_currency_setting_free_before_first_purchase(self):
        store = StoreSettings.objects.create(store_name="S")
        store.base_currency = "USD"
        store.save()
        store.refresh_from_db()
        self.assertEqual(store.base_currency, "USD")


class PurchaseLineOwnershipTests(TestCase):
    def setUp(self):
        create_currencies()
        self.supplier = Party.objects.create(name="Supplier A", is_supplier=True)
        self.owner = Party.objects.create(name="Owner", is_owner=True)
        self.partner = Party.objects.create(name="Partner", is_partner=True)
        category = Category.objects.create(name="Laptop")
        product = Product.objects.create(category=category, model_name="x")
        variant = Variant.objects.create(product=product)
        purchase = Purchase.objects.create(
            supplier=self.supplier, date=date(2026, 10, 5)
        )
        self.line = PurchaseLine.objects.create(
            purchase=purchase, variant=variant, qty=2, unit_price=Decimal("10")
        )

    def share(self, party, percent):
        return PurchaseLineOwnership.objects.create(
            line=self.line, party=party, share_percent=Decimal(percent)
        )

    def test_default_is_hundred_percent_owner(self):
        self.assertEqual(self.line.resolve_ownership(), [(self.owner, Decimal("100"))])

    def test_no_owner_defined_rejected(self):
        Party.objects.filter(pk=self.owner.pk).update(is_owner=False)
        with self.assertRaises(ValidationError):
            self.line.resolve_ownership()

    def test_explicit_shares_are_returned(self):
        self.share(self.owner, "60")
        self.share(self.partner, "40")
        self.assertEqual(
            self.line.resolve_ownership(),
            [(self.owner, Decimal("60")), (self.partner, Decimal("40"))],
        )

    def test_total_below_hundred_rejected(self):
        self.share(self.owner, "60")
        self.share(self.partner, "30")
        with self.assertRaises(ValidationError):
            self.line.resolve_ownership()

    def test_total_above_hundred_rejected(self):
        self.share(self.owner, "70")
        self.share(self.partner, "40")
        with self.assertRaises(ValidationError):
            self.line.resolve_ownership()

    def test_uneven_split_summing_to_hundred_accepted(self):
        third = Party.objects.create(name="Third", is_partner=True)
        self.share(self.owner, "33.33")
        self.share(self.partner, "33.33")
        self.share(third, "33.34")
        self.assertEqual(len(self.line.resolve_ownership()), 3)

    def test_valid_share_accepted(self):
        PurchaseLineOwnership(
            line=self.line, party=self.partner, share_percent=Decimal("50")
        ).full_clean()

    def test_share_range(self):
        for value in ["0.01", "50", "100"]:
            with self.subTest(value=value):
                PurchaseLineOwnership(
                    line=self.line, party=self.partner, share_percent=Decimal(value)
                ).full_clean()
        for value in ["0", "-5", "100.01"]:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    PurchaseLineOwnership(
                        line=self.line, party=self.partner, share_percent=Decimal(value)
                    ).full_clean()

    def test_party_without_ownership_role_rejected(self):
        with self.assertRaises(ValidationError):
            PurchaseLineOwnership(
                line=self.line, party=self.supplier, share_percent=Decimal("50")
            ).full_clean()

    def test_duplicate_party_on_same_line_rejected(self):
        self.share(self.partner, "30")
        second = PurchaseLineOwnership(
            line=self.line, party=self.partner, share_percent=Decimal("20")
        )
        with self.assertRaises(ValidationError):
            second.full_clean()

    def test_deleting_line_deletes_its_shares(self):
        self.share(self.partner, "100")
        self.line.delete()
        self.assertEqual(PurchaseLineOwnership.objects.count(), 0)

    def test_cannot_delete_party_with_shares(self):
        self.share(self.partner, "100")
        with self.assertRaises(ProtectedError):
            self.partner.delete()

    def test_str(self):
        row = self.share(self.partner, "40")
        row.refresh_from_db()
        self.assertEqual(str(row), "Partner: 40.00%")


class PurchaseLockBase(TestCase):
    Status = Purchase.Status

    def setUp(self):
        create_currencies()
        self.supplier = Party.objects.create(name="Supplier A", is_supplier=True)
        self.other_supplier = Party.objects.create(name="Supplier B", is_supplier=True)
        self.partner = Party.objects.create(name="Partner", is_partner=True)
        category = Category.objects.create(name="Laptop")
        product = Product.objects.create(category=category, model_name="x")
        self.variant = Variant.objects.create(product=product)
        self.purchase = self.new_purchase()

    def new_purchase(self, **overrides):
        data = {
            "supplier": self.supplier,
            "date": date(2026, 10, 5),
            "invoice_no": "A1",
            "note": "n",
        }
        data.update(overrides)
        return Purchase.objects.create(**data)

    def add_line(self, purchase=None):
        return PurchaseLine.objects.create(
            purchase=purchase or self.purchase,
            variant=self.variant,
            unit_price=Decimal("10"),
        )

    def force_status(self, purchase, status):
        """وضعیت را مستقیم در دیتابیس عوض می‌کند، بدون عبور از قاعده‌ها."""
        Purchase.objects.filter(pk=purchase.pk).update(status=status)
        purchase.refresh_from_db()


class PurchaseStatusTransitionTests(PurchaseLockBase):
    def test_draft_to_confirmed_allowed(self):
        self.purchase.status = self.Status.CONFIRMED
        self.purchase.save()
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, self.Status.CONFIRMED)

    def test_confirmed_to_cancelled_allowed(self):
        self.force_status(self.purchase, self.Status.CONFIRMED)
        self.purchase.status = self.Status.CANCELLED
        self.purchase.save()
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, self.Status.CANCELLED)

    def test_forbidden_transitions_rejected_on_save(self):
        S = self.Status
        forbidden = [
            (S.DRAFT, S.CANCELLED),
            (S.CONFIRMED, S.DRAFT),
            (S.CANCELLED, S.DRAFT),
            (S.CANCELLED, S.CONFIRMED),
        ]
        for start, target in forbidden:
            with self.subTest(start=start, target=target):
                self.force_status(self.purchase, start)
                self.purchase.status = target
                with self.assertRaises(ValidationError):
                    self.purchase.save()
                self.purchase.refresh_from_db()
                self.assertEqual(self.purchase.status, start)

    def test_forbidden_transition_rejected_in_clean(self):
        self.force_status(self.purchase, self.Status.CONFIRMED)
        self.purchase.status = self.Status.DRAFT
        with self.assertRaises(ValidationError):
            self.purchase.full_clean()

    def test_saving_with_unchanged_status_is_fine(self):
        for status in self.Status:
            with self.subTest(status=status):
                self.force_status(self.purchase, status)
                self.purchase.save()
                self.purchase.refresh_from_db()
                self.assertEqual(self.purchase.status, status)

    def test_is_draft(self):
        self.assertTrue(self.purchase.is_draft)
        self.force_status(self.purchase, self.Status.CONFIRMED)
        self.assertFalse(self.purchase.is_draft)

    def test_new_purchase_counts_as_draft(self):
        self.assertTrue(Purchase(supplier=self.supplier).is_draft)


class PurchaseFieldLockTests(PurchaseLockBase):
    def changes(self):
        return {
            "supplier": self.other_supplier,
            "date": date(2026, 10, 6),
            "currency": "USD",
            "exchange_rate": Decimal("2"),
        }

    def test_draft_fields_are_editable(self):
        for field, value in self.changes().items():
            with self.subTest(field=field):
                setattr(self.purchase, field, value)
                self.purchase.save()
                self.purchase.refresh_from_db()
                self.assertEqual(getattr(self.purchase, field), value)

    def test_locked_fields_rejected_after_confirmation_or_cancellation(self):
        for status in (self.Status.CONFIRMED, self.Status.CANCELLED):
            for field, value in self.changes().items():
                with self.subTest(status=status, field=field):
                    self.force_status(self.purchase, status)
                    original = getattr(self.purchase, field)
                    setattr(self.purchase, field, value)
                    with self.assertRaises(ValidationError):
                        self.purchase.save()
                    self.purchase.refresh_from_db()
                    self.assertEqual(getattr(self.purchase, field), original)

    def test_locked_field_rejected_in_clean_after_confirmation(self):
        self.force_status(self.purchase, self.Status.CONFIRMED)
        self.purchase.supplier = self.other_supplier
        with self.assertRaises(ValidationError):
            self.purchase.full_clean()

    def test_invoice_no_and_note_stay_editable_after_confirmation(self):
        self.force_status(self.purchase, self.Status.CONFIRMED)
        self.purchase.invoice_no = "B2"
        self.purchase.note = "changed"
        self.purchase.save()
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.invoice_no, "B2")
        self.assertEqual(self.purchase.note, "changed")

    def test_unchanged_confirmed_purchase_passes_full_clean(self):
        self.force_status(self.purchase, self.Status.CONFIRMED)
        self.purchase.full_clean()

    def test_confirmed_purchase_passes_full_clean_after_currency_deactivated(self):
        purchase = self.new_purchase(currency="USD", exchange_rate=Decimal("100000"))
        self.force_status(purchase, self.Status.CONFIRMED)
        Currency.objects.filter(code="USD").update(is_active=False)
        purchase.full_clean()


class PurchaseDeleteLockTests(PurchaseLockBase):
    def test_draft_purchase_can_be_deleted(self):
        self.purchase.delete()
        self.assertEqual(Purchase.objects.count(), 0)

    def test_confirmed_or_cancelled_purchase_cannot_be_deleted(self):
        for status in (self.Status.CONFIRMED, self.Status.CANCELLED):
            with self.subTest(status=status):
                self.force_status(self.purchase, status)
                with self.assertRaises(ValidationError):
                    self.purchase.delete()
                self.assertTrue(Purchase.objects.filter(pk=self.purchase.pk).exists())


class PurchaseLineLockTests(PurchaseLockBase):
    def test_draft_lines_can_be_added_edited_and_deleted(self):
        line = self.add_line()
        line.qty = 5
        line.save()
        line.refresh_from_db()
        self.assertEqual(line.qty, 5)
        line.delete()
        self.assertEqual(PurchaseLine.objects.count(), 0)

    def test_cannot_add_line_after_confirmation(self):
        for status in (self.Status.CONFIRMED, self.Status.CANCELLED):
            with self.subTest(status=status):
                self.force_status(self.purchase, status)
                with self.assertRaises(ValidationError):
                    self.add_line()
                self.assertEqual(PurchaseLine.objects.count(), 0)

    def test_new_line_fails_full_clean_after_confirmation(self):
        self.force_status(self.purchase, self.Status.CONFIRMED)
        line = PurchaseLine(
            purchase=self.purchase, variant=self.variant, unit_price=Decimal("10")
        )
        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_cannot_edit_line_after_confirmation(self):
        for status in (self.Status.CONFIRMED, self.Status.CANCELLED):
            with self.subTest(status=status):
                line = self.add_line()
                self.force_status(self.purchase, status)
                line.qty = 9
                with self.assertRaises(ValidationError):
                    line.save()
                line.refresh_from_db()
                self.assertEqual(line.qty, 1)
                Purchase.objects.filter(pk=self.purchase.pk).update(
                    status=self.Status.DRAFT
                )
                line.delete()

    def test_edited_line_fails_full_clean_after_confirmation(self):
        line = self.add_line()
        self.force_status(self.purchase, self.Status.CONFIRMED)
        line.qty = 9
        with self.assertRaises(ValidationError):
            line.full_clean()

    def test_unchanged_line_of_confirmed_purchase_cannot_be_saved(self):
        line = self.add_line()
        self.force_status(self.purchase, self.Status.CONFIRMED)
        with self.assertRaises(ValidationError):
            line.save()

    def test_cannot_delete_line_after_confirmation(self):
        line = self.add_line()
        self.force_status(self.purchase, self.Status.CONFIRMED)
        with self.assertRaises(ValidationError):
            line.delete()
        self.assertEqual(PurchaseLine.objects.count(), 1)

    def test_cannot_move_line_into_confirmed_purchase(self):
        confirmed = self.new_purchase(invoice_no="C")
        self.force_status(confirmed, self.Status.CONFIRMED)
        line = self.add_line()
        line.purchase = confirmed
        with self.assertRaises(ValidationError):
            line.save()

    def test_cannot_move_line_out_of_confirmed_purchase(self):
        confirmed = self.new_purchase(invoice_no="C")
        line = self.add_line(confirmed)
        self.force_status(confirmed, self.Status.CONFIRMED)
        line.purchase = self.purchase
        with self.assertRaises(ValidationError):
            line.save()

    def test_can_move_line_between_draft_purchases(self):
        other = self.new_purchase(invoice_no="D")
        line = self.add_line()
        line.purchase = other
        line.save()
        line.refresh_from_db()
        self.assertEqual(line.purchase_id, other.pk)


class PurchaseLineOwnershipLockTests(PurchaseLockBase):
    def setUp(self):
        super().setUp()
        self.line = self.add_line()

    def add_share(self):
        return PurchaseLineOwnership.objects.create(
            line=self.line, party=self.partner, share_percent=Decimal("50")
        )

    def test_draft_shares_can_be_added_edited_and_deleted(self):
        share = self.add_share()
        share.share_percent = Decimal("60")
        share.save()
        share.refresh_from_db()
        self.assertEqual(share.share_percent, Decimal("60"))
        share.delete()
        self.assertEqual(PurchaseLineOwnership.objects.count(), 0)

    def test_cannot_add_share_after_confirmation(self):
        self.force_status(self.purchase, self.Status.CONFIRMED)
        with self.assertRaises(ValidationError):
            self.add_share()
        self.assertEqual(PurchaseLineOwnership.objects.count(), 0)

    def test_new_share_fails_full_clean_after_confirmation(self):
        self.force_status(self.purchase, self.Status.CONFIRMED)
        share = PurchaseLineOwnership(
            line=self.line, party=self.partner, share_percent=Decimal("50")
        )
        with self.assertRaises(ValidationError):
            share.full_clean()

    def test_cannot_edit_share_after_confirmation(self):
        share = self.add_share()
        self.force_status(self.purchase, self.Status.CONFIRMED)
        share.share_percent = Decimal("60")
        with self.assertRaises(ValidationError):
            share.save()
        share.refresh_from_db()
        self.assertEqual(share.share_percent, Decimal("50"))

    def test_edited_share_fails_full_clean_after_confirmation(self):
        share = self.add_share()
        self.force_status(self.purchase, self.Status.CONFIRMED)
        share.share_percent = Decimal("60")
        with self.assertRaises(ValidationError):
            share.full_clean()

    def test_cannot_delete_share_after_confirmation(self):
        share = self.add_share()
        self.force_status(self.purchase, self.Status.CONFIRMED)
        with self.assertRaises(ValidationError):
            share.delete()
        self.assertEqual(PurchaseLineOwnership.objects.count(), 1)
