from django.conf import settings
from django.db import models


class TimeStamped(models.Model):
    """فیلدهای مشترک همه‌ی مدل‌ها."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Party(TimeStamped):
    """طرف حساب: تأمین‌کننده، مشتری، شریک، فروشنده."""

    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30, blank=True)
    note = models.TextField(blank=True)

    is_supplier = models.BooleanField(default=False)
    is_customer = models.BooleanField(default=False)
    is_partner = models.BooleanField(default=False)
    is_seller = models.BooleanField(default=False)

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="party",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class StoreSettings(models.Model):
    """تنظیمات فروشگاه (باید فقط یک رکورد داشته باشد)."""

    class ProfitMode(models.TextChoices):
        BASE = "base", "تومانی"
        FX = "fx", "ارزی"

    class CostingMethod(models.TextChoices):
        WAVG = "wavg", "میانگین موزون"
        FIFO = "fifo", "FIFO"

    store_name = models.CharField(max_length=50, verbose_name="نام فروشگاه")
    base_currency = models.CharField(
        max_length=5, default="IRT", verbose_name="ارز پایه"
    )
    profit_mode = models.CharField(
        max_length=4,
        choices=ProfitMode.choices,
        default=ProfitMode.BASE,
        verbose_name="حالت محاسبه‌ی سود",
    )
    costing_method = models.CharField(
        max_length=10,
        choices=CostingMethod.choices,
        default=CostingMethod.WAVG,
        verbose_name="روش محاسبه‌ی بهای تمام‌شده",
    )
    enabled_modules = models.JSONField(
        default=list, blank=True, verbose_name="ماژول‌های فعال"
    )

    class Meta:
        verbose_name = "تنظیمات فروشگاه"
        verbose_name_plural = "تنظیمات فروشگاه"

    def __str__(self):
        return self.store_name
