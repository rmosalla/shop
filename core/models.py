from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


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
        ordering = ("name",)

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

    def has_module(self, module_name):
        return module_name in self.enabled_modules

    def _ensure_single_instance(self):
        if self.pk is None and StoreSettings.objects.exists():
            raise ValidationError("فقط یک فروشگاه می‌توانید در تنظیمات فروشگاه ثبت کنید")

    def save(self, *args, **kwargs):
        self._ensure_single_instance()
        super().save(*args, **kwargs)

    def clean(self, *args, **kwargs):
        self._ensure_single_instance()
        super().clean()

    @classmethod
    def get_solo(cls):
        store = cls.objects.first()
        if store is None:
            store = cls.objects.create(store_name="فروشگاه من")
        return store

    class Meta:
        verbose_name = "تنظیمات فروشگاه"
        verbose_name_plural = "تنظیمات فروشگاه"

    def __str__(self):
        return self.store_name


class Period(TimeStamped):
    """دوره‌ی زمانی تسویه (مثلا یک ماه)."""

    class Status(models.TextChoices):
        OPEN = "open", "باز"
        CLOSED = "closed", "بسته"

    name = models.CharField(max_length=100, verbose_name="نام دوره")
    start_date = models.DateField(verbose_name="تاریخ شروع")
    end_date = models.DateField(verbose_name="تاریخ پایان")
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.OPEN,
        verbose_name="وضعیت",
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان بسته‌شدن",
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        verbose_name="بسته‌شده توسط",
    )

    def clean(self):
        if self.start_date > self.end_date:
            raise ValidationError("تاریخ پایان نمی‌تواند کوچک‌تر از تاریخ شروع باشد")
        super().clean()

    def close(self, user):
        if self.status == self.Status.CLOSED:
            raise ValidationError("این دوره قبلا بسته شده است")
        self.status = self.Status.CLOSED
        self.closed_at = timezone.now()
        self.closed_by = user
        self.save()

    @classmethod
    def assert_date_open(cls, target_date):
        is_locked = cls.objects.filter(
            start_date__lte=target_date,
            end_date__gte=target_date,
            status=cls.Status.CLOSED,
        ).exists()
        if is_locked:
            raise ValidationError(
                "تاریخ در دوره بسته‌شده است. تاریخ را اصلاح کنید یا سند برگشت ثبت کنید."
            )

    class Meta:
        ordering = ("-start_date",)
        verbose_name = "دوره"
        verbose_name_plural = "دوره‌ها"

    def __str__(self):
        return self.name
