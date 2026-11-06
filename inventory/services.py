from django.core.exceptions import ValidationError
from django.db import transaction

from core.models import Period, round_to_base
from purchasing.models import Purchase

from .models import Unit, UnitOwnership


def confirm_purchase(purchase):
    """فاکتور پیش‌نویس را ثبت می‌کند و برای هر عدد یک دستگاه می‌سازد."""
    with transaction.atomic():
        if purchase.pk is None or not purchase.is_draft:
            raise ValidationError("فقط فاکتور پیش‌نویس قابل ثبت است")
        purchase.full_clean()
        lines = list(purchase.lines.select_related("variant__product"))
        if not lines:
            raise ValidationError("فاکتور بدون ردیف قابل ثبت نیست")
        units = []
        for line in lines:
            line.full_clean()
            shares = line.resolve_ownership()
            for _ in range(line.qty):
                unit = Unit(
                    variant=line.variant,
                    purchase_line=line,
                    cost_amount=line.unit_price,
                    cost_currency=purchase.currency,
                    cost_rate=purchase.exchange_rate,
                    cost_base=round_to_base(line.unit_price * purchase.exchange_rate),
                    in_stock_since=purchase.date,
                )
                unit.full_clean()
                unit.save()
                for party, percent in shares:
                    UnitOwnership.objects.create(
                        unit=unit, party=party, share_percent=percent
                    )
                units.append(unit)
        purchase.status = Purchase.Status.CONFIRMED
        purchase.save()
        return units


def cancel_purchase(purchase):
    """فاکتور ثبت‌شده را باطل می‌کند و دستگاه‌های آن را خارج می‌کند."""
    with transaction.atomic():
        is_confirmed = Purchase.objects.filter(
            pk=purchase.pk, status=Purchase.Status.CONFIRMED
        ).exists()
        if not is_confirmed:
            raise ValidationError("فقط فاکتور ثبت‌شده قابل ابطال است")
        Period.assert_date_open(purchase.date)
        units = list(Unit.objects.filter(purchase_line__purchase=purchase))
        blocked = [unit for unit in units if unit.status != Unit.Status.IN_STOCK]
        if blocked:
            codes = "، ".join(unit.uid for unit in blocked)
            raise ValidationError(
                f"دستگاه‌های زیر دیگر موجود نیستند و فاکتور قابل ابطال نیست: {codes}"
            )
        for unit in units:
            unit.status = Unit.Status.WRITTEN_OFF
            unit.save()
        purchase.status = Purchase.Status.CANCELLED
        purchase.save()
        return units
