from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError

from core.models import Period
from purchasing.models import Purchase

from .models import Unit, UnitOwnership
from .services import cancel_purchase, confirm_purchase
from .test_confirm import ConfirmPurchaseBase


class CancelPurchaseBase(ConfirmPurchaseBase):
    def confirmed(self, qty=2):
        self.add_line(qty=qty)
        return confirm_purchase(self.purchase)

    def statuses(self):
        return {unit.pk: unit.status for unit in Unit.objects.all()}

    def assert_rejected_and_unchanged(self, purchase=None):
        purchase = purchase or self.purchase
        before = self.statuses()
        ownerships = UnitOwnership.objects.count()
        with self.assertRaises(ValidationError):
            cancel_purchase(purchase)
        self.assertEqual(self.statuses(), before)
        self.assertEqual(UnitOwnership.objects.count(), ownerships)
        purchase.refresh_from_db()
        self.assertNotEqual(purchase.status, Purchase.Status.CANCELLED)


class CancelPurchaseSuccessTests(CancelPurchaseBase):
    def test_purchase_becomes_cancelled(self):
        self.confirmed()
        cancel_purchase(self.purchase)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, Purchase.Status.CANCELLED)

    def test_units_are_written_off_not_deleted(self):
        units = self.confirmed(qty=3)
        cancel_purchase(self.purchase)
        self.assertEqual(Unit.objects.count(), 3)
        for unit in Unit.objects.filter(pk__in=[u.pk for u in units]):
            self.assertEqual(unit.status, Unit.Status.WRITTEN_OFF)

    def test_returns_the_written_off_units(self):
        created = self.confirmed(qty=2)
        returned = cancel_purchase(self.purchase)
        self.assertEqual({u.pk for u in returned}, {u.pk for u in created})

    def test_units_keep_their_uid_cost_and_ownership(self):
        created = self.confirmed(qty=1)
        uid = created[0].uid
        cancel_purchase(self.purchase)
        unit = Unit.objects.get()
        self.assertEqual(unit.uid, uid)
        self.assertEqual(unit.cost_base, Decimal("1500000"))
        self.assertEqual(unit.ownership_total, Decimal("100"))

    def test_serial_numbers_do_not_block_cancellation(self):
        self.confirmed(qty=1)
        Unit.objects.update(serial_number="SN-1")
        cancel_purchase(self.purchase)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, Purchase.Status.CANCELLED)

    def test_other_purchases_are_untouched(self):
        self.confirmed(qty=2)
        other = self.new_purchase(invoice_no="B")
        self.add_line(qty=1, purchase=other)
        confirm_purchase(other)
        cancel_purchase(self.purchase)
        other_unit = Unit.objects.get(purchase_line__purchase=other)
        self.assertEqual(other_unit.status, Unit.Status.IN_STOCK)
        other.refresh_from_db()
        self.assertEqual(other.status, Purchase.Status.CONFIRMED)

    def test_cancelled_purchase_stays_locked(self):
        self.confirmed()
        cancel_purchase(self.purchase)
        with self.assertRaises(ValidationError):
            self.add_line()
        with self.assertRaises(ValidationError):
            self.purchase.delete()

    def test_cancelled_purchase_cannot_be_confirmed_again(self):
        self.confirmed()
        cancel_purchase(self.purchase)
        with self.assertRaises(ValidationError):
            confirm_purchase(self.purchase)

    def test_variant_stays_locked_after_cancellation(self):
        self.confirmed()
        cancel_purchase(self.purchase)
        self.assertTrue(self.variant.has_documents())


class CancelPurchaseRejectionTests(CancelPurchaseBase):
    def test_draft_purchase(self):
        self.add_line()
        with self.assertRaises(ValidationError):
            cancel_purchase(self.purchase)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, Purchase.Status.DRAFT)

    def test_unsaved_purchase(self):
        unsaved = Purchase(supplier=self.supplier, date=date(2026, 10, 5))
        with self.assertRaises(ValidationError):
            cancel_purchase(unsaved)

    def test_already_cancelled_purchase(self):
        self.confirmed()
        cancel_purchase(self.purchase)
        with self.assertRaises(ValidationError):
            cancel_purchase(self.purchase)

    def test_in_memory_status_is_not_trusted(self):
        self.add_line()
        self.purchase.status = Purchase.Status.CONFIRMED
        with self.assertRaises(ValidationError):
            cancel_purchase(self.purchase)

    def test_sold_unit_blocks_cancellation(self):
        self.confirmed(qty=2)
        Unit.objects.filter(pk=Unit.objects.first().pk).update(status=Unit.Status.SOLD)
        self.assert_rejected_and_unchanged()

    def test_reserved_unit_blocks_cancellation(self):
        self.confirmed(qty=2)
        Unit.objects.filter(pk=Unit.objects.first().pk).update(
            status=Unit.Status.RESERVED
        )
        self.assert_rejected_and_unchanged()

    def test_already_written_off_unit_blocks_cancellation(self):
        self.confirmed(qty=2)
        Unit.objects.filter(pk=Unit.objects.first().pk).update(
            status=Unit.Status.WRITTEN_OFF
        )
        self.assert_rejected_and_unchanged()

    def test_sold_unit_in_second_line_blocks_everything(self):
        self.add_line(qty=2)
        self.add_line(qty=1, price="1600000")
        confirm_purchase(self.purchase)
        last = Unit.objects.order_by("-pk").first()
        Unit.objects.filter(pk=last.pk).update(status=Unit.Status.SOLD)
        self.assert_rejected_and_unchanged()

    def test_error_message_names_the_blocking_unit(self):
        self.confirmed(qty=1)
        unit = Unit.objects.get()
        Unit.objects.filter(pk=unit.pk).update(status=Unit.Status.SOLD)
        with self.assertRaises(ValidationError) as caught:
            cancel_purchase(self.purchase)
        self.assertIn(unit.uid, str(caught.exception))

    def test_closed_period_blocks_cancellation(self):
        self.confirmed()
        Period.objects.create(
            name="october",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 30),
            status=Period.Status.CLOSED,
        )
        self.assert_rejected_and_unchanged()
