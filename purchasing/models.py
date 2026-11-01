from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from catalog.models import Variant
from core.models import Currency, Party, Period, StoreSettings, TimeStamped


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
        super().save(*args, **kwargs)

    def clean(self):
        self._normalize_currency()
        if self.date is not None:
            Period.assert_date_open(self.date)
        self._ensure_currency_is_available()
        self._ensure_rate_matches_currency()
        super().clean()

    def get_currency(self):
        """رکورد ارز این فاکتور در جدول ارزها (یا None)."""
        return Currency.objects.filter(code=self.currency).first()

    def _ensure_currency_is_available(self):
        if not Currency.objects.filter(code=self.currency, is_active=True).exists():
            raise ValidationError({"currency": "این ارز تعریف نشده یا غیرفعال است."})

    def _normalize_currency(self):
        self.currency = (self.currency or "").strip().upper()

    def _ensure_rate_matches_currency(self):
        base_currency = (
            StoreSettings.objects.values_list("base_currency", flat=True).first()
            or "IRT"
        )
        if self.currency == base_currency.upper() and self.exchange_rate != 1:
            raise ValidationError(
                {"exchange_rate": "برای ارز پایه‌ی فروشگاه، نرخ ارز باید ۱ باشد."}
            )

    @property
    def total(self):
        """جمع total همه‌ی ردیف‌ها"""
        return sum((line.total for line in self.lines.all()), Decimal("0"))

    @property
    def total_base(self):
        """جمع total_base همه‌ی ردیف‌ه"""
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

    def clean(self):
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

    @property
    def total(self):
        """تعداد × قیمت واحد، به ارز فاکتور"""
        return self.qty * self.unit_price

    @property
    def total_base(self):
        """مبلغ به ارز پایه، گرد شده تا دو رقم اعشار"""
        result = self.total * self.purchase.exchange_rate

        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
