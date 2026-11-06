from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from catalog.models import Category, Product, Variant
from core.models import Currency, Party, Period
from purchasing.models import Purchase, PurchaseLine, PurchaseLineOwnership

from .models import Unit, UnitOwnership
from .services import confirm_purchase


class ConfirmPurchaseBase(TestCase):
    def setUp(self):
        Currency.objects.create(code="IRT", name="تومان", decimal_places=0)
        Currency.objects.create(code="AED", name="درهم")
        self.owner = Party.objects.create(name="Owner", is_owner=True)
        self.partner = Party.objects.create(name="Partner", is_partner=True)
        self.supplier = Party.objects.create(name="Supplier A", is_supplier=True)
        self.category = Category.objects.create(name="Laptop")
        product = Product.objects.create(
            category=self.category, brand="Dell", model_name="Latitude 5420"
        )
        self.variant = Variant.objects.create(product=product)
        self.purchase = self.new_purchase()

    def new_purchase(self, **overrides):
        data = {"supplier": self.supplier, "date": date(2026, 10, 5)}
        data.update(overrides)
        return Purchase.objects.create(**data)

    def add_line(self, qty=2, price="1500000", variant=None, purchase=None):
        return PurchaseLine.objects.create(
            purchase=purchase or self.purchase,
            variant=variant or self.variant,
            qty=qty,
            unit_price=Decimal(price),
        )

    def quantity_variant(self):
        product = Product.objects.create(
            category=self.category,
            model_name="Mouse",
            tracking_type=Product.Tracking.QUANTITY,
        )
        return Variant.objects.create(product=product)

    def assert_rejected_and_nothing_changed(self):
        with self.assertRaises(ValidationError):
            confirm_purchase(self.purchase)
        self.assertEqual(Unit.objects.count(), 0)
        self.assertEqual(UnitOwnership.objects.count(), 0)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, Purchase.Status.DRAFT)


class ConfirmPurchaseSuccessTests(ConfirmPurchaseBase):
    def test_creates_one_unit_per_piece(self):
        line = self.add_line(qty=3)
        confirm_purchase(self.purchase)
        self.assertEqual(Unit.objects.count(), 3)
        for unit in Unit.objects.all():
            self.assertEqual(unit.variant, self.variant)
            self.assertEqual(unit.purchase_line, line)

    def test_returns_created_units(self):
        self.add_line(qty=3)
        units = confirm_purchase(self.purchase)
        self.assertEqual(len(units), 3)
        self.assertTrue(all(isinstance(unit, Unit) for unit in units))
        self.assertEqual({u.pk for u in units}, {u.pk for u in Unit.objects.all()})

    def test_purchase_becomes_confirmed(self):
        self.add_line()
        confirm_purchase(self.purchase)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, Purchase.Status.CONFIRMED)

    def test_unit_starts_in_stock_with_purchase_date(self):
        self.add_line(qty=1)
        confirm_purchase(self.purchase)
        unit = Unit.objects.get()
        self.assertEqual(unit.status, Unit.Status.IN_STOCK)
        self.assertEqual(unit.condition, Unit.Condition.NEW)
        self.assertEqual(unit.serial_number, "")
        self.assertEqual(unit.in_stock_since, date(2026, 10, 5))

    def test_cost_copied_for_base_currency(self):
        self.add_line(qty=1, price="1500000")
        confirm_purchase(self.purchase)
        unit = Unit.objects.get()
        self.assertEqual(unit.cost_amount, Decimal("1500000"))
        self.assertEqual(unit.cost_currency, "IRT")
        self.assertEqual(unit.cost_rate, Decimal("1"))
        self.assertEqual(unit.cost_base, Decimal("1500000"))

    def test_cost_for_foreign_currency(self):
        purchase = self.new_purchase(currency="AED", exchange_rate=Decimal("2.5"))
        self.add_line(qty=1, price="10.10", purchase=purchase)
        confirm_purchase(purchase)
        unit = Unit.objects.get()
        self.assertEqual(unit.cost_amount, Decimal("10.10"))
        self.assertEqual(unit.cost_currency, "AED")
        self.assertEqual(unit.cost_rate, Decimal("2.5"))
        self.assertEqual(unit.cost_base, Decimal("25"))

    def test_cost_base_rounds_half_up(self):
        purchase = self.new_purchase(currency="AED", exchange_rate=Decimal("2.5"))
        self.add_line(qty=1, price="9.80", purchase=purchase)
        confirm_purchase(purchase)
        self.assertEqual(Unit.objects.get().cost_base, Decimal("25"))

    def test_each_line_gets_its_own_units(self):
        first = self.add_line(qty=2)
        second = self.add_line(qty=1, price="1600000")
        confirm_purchase(self.purchase)
        self.assertEqual(Unit.objects.filter(purchase_line=first).count(), 2)
        self.assertEqual(Unit.objects.filter(purchase_line=second).count(), 1)
        self.assertEqual(
            Unit.objects.get(purchase_line=second).cost_amount, Decimal("1600000")
        )

    def test_default_ownership_is_owner_hundred_percent(self):
        self.add_line(qty=2)
        confirm_purchase(self.purchase)
        for unit in Unit.objects.all():
            shares = list(unit.ownerships.all())
            self.assertEqual(len(shares), 1)
            self.assertEqual(shares[0].party, self.owner)
            self.assertEqual(shares[0].share_percent, Decimal("100"))

    def test_explicit_ownership_is_copied_to_every_unit(self):
        line = self.add_line(qty=2)
        PurchaseLineOwnership.objects.create(
            line=line, party=self.owner, share_percent=Decimal("60")
        )
        PurchaseLineOwnership.objects.create(
            line=line, party=self.partner, share_percent=Decimal("40")
        )
        confirm_purchase(self.purchase)
        expected = {self.owner.pk: Decimal("60"), self.partner.pk: Decimal("40")}
        for unit in Unit.objects.all():
            actual = {s.party_id: s.share_percent for s in unit.ownerships.all()}
            self.assertEqual(actual, expected)
            self.assertEqual(unit.ownership_total, Decimal("100"))

    def test_unit_uids_are_unique_and_set(self):
        self.add_line(qty=3)
        units = confirm_purchase(self.purchase)
        uids = {unit.uid for unit in units}
        self.assertNotIn(None, uids)
        self.assertEqual(len(uids), 3)

    def test_lines_are_locked_afterwards(self):
        self.add_line()
        confirm_purchase(self.purchase)
        with self.assertRaises(ValidationError):
            self.add_line()


class ConfirmPurchaseRejectionTests(ConfirmPurchaseBase):
    def test_purchase_without_lines(self):
        self.assert_rejected_and_nothing_changed()

    def test_unsaved_purchase(self):
        unsaved = Purchase(supplier=self.supplier, date=date(2026, 10, 5))
        with self.assertRaises(ValidationError):
            confirm_purchase(unsaved)
        self.assertEqual(Unit.objects.count(), 0)

    def test_already_confirmed_purchase(self):
        self.add_line(qty=2)
        confirm_purchase(self.purchase)
        with self.assertRaises(ValidationError):
            confirm_purchase(self.purchase)
        self.assertEqual(Unit.objects.count(), 2)

    def test_cancelled_purchase(self):
        self.add_line()
        Purchase.objects.filter(pk=self.purchase.pk).update(
            status=Purchase.Status.CANCELLED
        )
        self.purchase.refresh_from_db()
        with self.assertRaises(ValidationError):
            confirm_purchase(self.purchase)
        self.assertEqual(Unit.objects.count(), 0)

    def test_date_in_closed_period(self):
        self.add_line()
        Period.objects.create(
            name="october",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 30),
            status=Period.Status.CLOSED,
        )
        self.assert_rejected_and_nothing_changed()

    def test_unknown_currency(self):
        self.purchase = self.new_purchase(currency="XYZ")
        self.add_line(purchase=self.purchase)
        self.assert_rejected_and_nothing_changed()

    def test_inactive_currency(self):
        self.purchase = self.new_purchase(currency="AED", exchange_rate=Decimal("2.5"))
        self.add_line(purchase=self.purchase)
        Currency.objects.filter(code="AED").update(is_active=False)
        self.assert_rejected_and_nothing_changed()

    def test_quantity_tracked_line(self):
        self.add_line(variant=self.quantity_variant())
        self.assert_rejected_and_nothing_changed()

    def test_nothing_is_created_when_a_later_line_fails(self):
        self.add_line(qty=2)
        self.add_line(qty=1, variant=self.quantity_variant())
        self.assert_rejected_and_nothing_changed()

    def test_ownership_total_not_hundred(self):
        line = self.add_line()
        PurchaseLineOwnership.objects.create(
            line=line, party=self.owner, share_percent=Decimal("60")
        )
        PurchaseLineOwnership.objects.create(
            line=line, party=self.partner, share_percent=Decimal("30")
        )
        self.assert_rejected_and_nothing_changed()

    def test_no_owner_defined(self):
        self.add_line()
        Party.objects.filter(pk=self.owner.pk).update(is_owner=False)
        self.assert_rejected_and_nothing_changed()
