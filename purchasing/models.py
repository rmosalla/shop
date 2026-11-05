from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from catalog.models import Variant
from core.models import (
    Currency,
    Party,
    Period,
    TimeStamped,
    get_base_currency_code,
    round_to_base,
)

ALLOWED_TRANSITIONS = {
    "draft": ("confirmed",),
    "confirmed": ("cancelled",),
    "cancelled": (),
}


class Purchase(TimeStamped):
    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        CONFIRMED = "confirmed", "ثبت‌شده"
        CANCELLED = "cancelled", "باطل"

    supplier = models.ForeignKey(
        Party,
        on_delete=models.PROTECT,
        limit_choices_to={"is_supplier": True},
        related_name="purchases",
        verbose_name="تأمین‌کننده",
    )
    date = models.DateField(verbose_name="تاریخ خرید")
    invoice_no = models.CharField(
        max_length=50, verbose_name="شماره فاکتور", blank=True
    )
    currency = models.CharField(default="IRT", max_length=5, verbose_name="ارز")
    exchange_rate = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=1,
        validators=[MinValueValidator(Decimal("0.0001"))],
        verbose_name="نرخ ارز",
        help_text=(
            "هر یک واحد ارز فاکتور چند واحد ارز پایه است؟ مثلاً برای دلار: ۲۷۵۰۰۰"
        ),
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        verbose_name="وضعیت",
        default=Status.DRAFT,
    )
    note = models.TextField(verbose_name="یادداشت", blank=True)

    class Meta:
        ordering = ("-date", "-id")
        verbose_name = "فاکتور خرید"
        verbose_name_plural = "فاکتورهای خرید"

    def __str__(self):
        return f"{self.supplier.name} - {self.date}"

    def save(self, *args, **kwargs):
        self._normalize_currency()
        self._ensure_valid_transition()
        self._ensure_fields_unlocked()
        super().save(*args, **kwargs)

    def clean(self):
        self._normalize_currency()
        self._ensure_valid_transition()
        self._ensure_fields_unlocked()
        if self.date is not None and self.is_draft:
            Period.assert_date_open(self.date)
        if self.is_draft:
            self._ensure_currency_is_available()
        self._ensure_rate_matches_currency()
        super().clean()

    def delete(self, *args, **kwargs):
        if not self.is_draft:
            raise ValidationError("فاکتور ثبت‌شده یا باطل قابل حذف نیست.")
        return super().delete(*args, **kwargs)

    def get_currency(self):
        """رکورد ارز این فاکتور در جدول ارزها (یا None)."""
        return Currency.objects.filter(code=self.currency).first()

    def _ensure_currency_is_available(self):
        if not Currency.objects.filter(code=self.currency, is_active=True).exists():
            raise ValidationError({"currency": "این ارز تعریف نشده یا غیرفعال است."})

    def _normalize_currency(self):
        self.currency = (self.currency or "").strip().upper()

    def _ensure_rate_matches_currency(self):
        if self.currency == get_base_currency_code() and self.exchange_rate != 1:
            raise ValidationError(
                {"exchange_rate": "برای ارز پایه‌ی فروشگاه، نرخ ارز باید ۱ باشد."}
            )

    def _stored_status(self):
        """وضعیت ذخیره‌شده در دیتابیس، یا None برای فاکتور جدید."""
        if self.pk is None:
            return None
        return (
            Purchase.objects.filter(pk=self.pk).values_list("status", flat=True).first()
        )

    def _ensure_valid_transition(self):
        stored = self._stored_status()
        if stored not in (None, self.status):
            if self.status not in ALLOWED_TRANSITIONS[stored]:
                raise ValidationError(
                    {
                        "status": f"تغییر وضعیت از «{self.Status(stored).label}» "
                        f"به «{self.Status(self.status).label}» مجاز نیست."
                    }
                )

    def _ensure_fields_unlocked(self):
        errors = {}
        status = self._stored_status()
        if status not in (None, self.Status.DRAFT):
            names = ("supplier_id", "date", "currency", "exchange_rate")
            stored_values = Purchase.objects.filter(pk=self.pk).values(*names).first()
            for name in names:
                if stored_values[name] != getattr(self, name):
                    errors[name.removesuffix("_id")] = (
                        "این فیلد بعد از ثبت فاکتور قابل تغییر نیست."
                    )
        if errors:
            raise ValidationError(errors)

    @property
    def is_draft(self):
        stored = self._stored_status()
        return stored in (None, self.Status.DRAFT)

    @property
    def total(self):
        """جمع total همه‌ی ردیف‌ها"""
        return sum((line.total for line in self.lines.all()), Decimal("0"))

    @property
    def total_base(self):
        """جمع total_base همه‌ی ردیف‌ها"""
        return sum((line.total_base for line in self.lines.all()), Decimal("0"))


class PurchaseLine(TimeStamped):
    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="فاکتور",
    )
    variant = models.ForeignKey(
        Variant,
        on_delete=models.PROTECT,
        related_name="purchase_lines",
        verbose_name="کانفیگ",
    )
    qty = models.PositiveIntegerField(
        default=1, validators=[MinValueValidator(1)], verbose_name="تعداد"
    )
    unit_price = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="قیمت واحد",
    )

    class Meta:
        ordering = ("id",)
        verbose_name = "ردیف فاکتور خرید"
        verbose_name_plural = "ردیف‌های فاکتور خرید"

    def __str__(self):
        return f"{self.variant.sku} x {self.qty}"

    def save(self, *args, **kwargs):
        self._ensure_purchase_is_draft()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._ensure_purchase_is_draft()
        return super().delete(*args, **kwargs)

    def clean(self):
        self._ensure_purchase_is_draft()
        if self.purchase_id is not None and isinstance(self.unit_price, Decimal):
            currency = self.purchase.get_currency()
            if (
                currency is not None
                and currency.round(self.unit_price) != self.unit_price
            ):
                raise ValidationError(
                    {
                        "unit_price": (
                            f"ارز {currency.code} حداکثر "
                            f"{currency.decimal_places} رقم اعشار دارد."
                        )
                    }
                )
        super().clean()

    def resolve_ownership(self):
        """فهرست (شخص، درصد) سهم‌ها. اگر چیزی ثبت نشده باشد ۱۰۰٪ صاحب فروشگاه."""
        rows = list(self.ownerships.select_related("party"))
        if rows:
            total = sum((row.share_percent for row in rows), Decimal("0"))
            if total != Decimal("100"):
                raise ValidationError(
                    f"مجموع سهم‌های ردیف باید ۱۰۰ باشد (الان {total} است)."
                )
            return [(row.party, row.share_percent) for row in rows]
        owners = list(Party.objects.filter(is_owner=True)[:2])
        if len(owners) != 1:
            raise ValidationError(
                "برای سهم پیش‌فرض باید دقیقاً یک نفر به‌عنوان صاحب فروشگاه تعریف شده باشد."
            )
        return [(owners[0], Decimal("100"))]

    def _stored_purchase_id(self):
        """شناسه‌ی فاکتور ذخیره‌شده در دیتابیس، یا None برای ردیف جدید."""
        if self.pk is None:
            return None
        return (
            PurchaseLine.objects.filter(pk=self.pk)
            .values_list("purchase_id", flat=True)
            .first()
        )

    def _ensure_purchase_is_draft(self):
        purchase_ids = {self.purchase_id, self._stored_purchase_id()} - {None}
        for purchase_id in purchase_ids:
            status = (
                Purchase.objects.filter(pk=purchase_id)
                .values_list("status", flat=True)
                .first()
            )
            if status != Purchase.Status.DRAFT:
                raise ValidationError(
                    {
                        "purchase": (
                            "فقط ردیف‌های فاکتور پیش‌نویس "
                            "قابل افزودن، ویرایش یا حذف هستند."
                        )
                    }
                )

    @property
    def total(self):
        """تعداد × قیمت واحد، به ارز فاکتور"""
        return self.qty * self.unit_price

    @property
    def total_base(self):
        """مبلغ به ارز پایه، گردشده بر اساس اعشار ارز پایه"""
        return round_to_base(self.total * self.purchase.exchange_rate)


class PurchaseLineOwnership(TimeStamped):
    """سهم یک شخص از دستگاه‌های یک ردیف فاکتور خرید."""

    line = models.ForeignKey(
        PurchaseLine,
        on_delete=models.CASCADE,
        related_name="ownerships",
        verbose_name="ردیف فاکتور",
    )
    party = models.ForeignKey(
        Party,
        on_delete=models.PROTECT,
        related_name="purchase_line_ownerships",
        verbose_name="شخص",
    )
    share_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01")), MaxValueValidator(100)],
        verbose_name="سهم (٪)",
    )

    class Meta:
        ordering = ("id",)
        constraints = (
            models.UniqueConstraint(
                fields=("line", "party"), name="uniq_line_ownership_party"
            ),
        )
        verbose_name = "سهم ردیف خرید"
        verbose_name_plural = "سهم‌های ردیف خرید"

    def __str__(self):
        return f"{self.party.name}: {self.share_percent}%"

    def save(self, *args, **kwargs):
        self._ensure_purchase_is_draft()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._ensure_purchase_is_draft()
        return super().delete(*args, **kwargs)

    def clean(self):
        self._ensure_purchase_is_draft()
        if self.party_id is not None and not self.party.can_own:
            raise ValidationError(
                {"party": "فقط صاحب فروشگاه یا شریک می‌تواند سهم داشته باشد."}
            )
        super().clean()

    def _stored_line_id(self):
        """شناسه‌ی ردیفی که این سهم به آن وصل است (یا None برای سهم جدید)."""
        if self.pk is None:
            return None
        return (
            PurchaseLineOwnership.objects.filter(pk=self.pk)
            .values_list("line_id", flat=True)
            .first()
        )

    def _ensure_purchase_is_draft(self):
        line_ids = {self.line_id, self._stored_line_id()} - {None}
        for line_id in line_ids:
            status = (
                Purchase.objects.filter(lines__pk=line_id)
                .values_list("status", flat=True)
                .first()
            )
            if status != Purchase.Status.DRAFT:
                raise ValidationError(
                    {
                        "line": (
                            "سهم‌ها فقط برای فاکتور پیش‌نویس "
                            "قابل افزودن، ویرایش یا حذف هستند."
                        )
                    }
                )
