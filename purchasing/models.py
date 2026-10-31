from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

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
        decimal_places=6,
        default=1,
        validators=[MinValueValidator(Decimal("0.000001"))],
        verbose_name="نرخ تبدیل",
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        verbose_name="وضعیت",
        default=Status.DRAFT,
    )
    note = models.TextField(max_length=200, verbose_name="یادداشت", blank=True)

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
