from decimal import ROUND_HALF_UP, Decimal

from django.core.validators import MinValueValidator
from django.db import models

from catalog.models import Variant
from core.models import Party, Period, TimeStamped


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
        verbose_name="نرخ تبدیل",
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

    def clean(self):
        if self.date is not None:
            Period.assert_date_open(self.date)
            super().clean()

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

    @property
    def total(self):
        """تعداد × قیمت واحد، به ارز فاکتور"""
        return self.qty * self.unit_price

    @property
    def total_base(self):
        """مبلغ به ارز پایه، گرد شده تا دو رقم اعشار"""
        result = self.total * self.purchase.exchange_rate

        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
