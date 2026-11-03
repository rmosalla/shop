from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, RegexValidator
from django.db import models
from django.utils import timezone


class TimeStamped(models.Model):
    """فیلدهای مشترک همه‌ی مدل‌ها."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Currency(TimeStamped):
    """ارزهای قابل استفاده در فروشگاه (ارز پایه و ارزهای خارجی)."""

    code = models.CharField(
        max_length=3,
        unique=True,
        validators=[
            RegexValidator(
                regex=r"^[A-Za-z]{3}$",
                message="کد ارز باید سه حرف انگلیسی باشد، مثل USD.",
                code="invalid_currency_code",
            )
        ],
        verbose_name="کد ارز",
    )
    name = models.CharField(max_length=50, verbose_name="نام")
    symbol = models.CharField(max_length=10, blank=True, verbose_name="نماد")
    decimal_places = models.PositiveSmallIntegerField(
        default=2,
        validators=[MaxValueValidator(2)],
        verbose_name="تعداد ارقام اعشار",
        help_text="۰ یعنی همیشه رند به عدد صحیح. حداکثر ۲.",
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        ordering = ("code",)
        verbose_name = "ارز"
        verbose_name_plural = "ارزها"

    def __str__(self):
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
        self._normalize_code()
        self._ensure_not_locked()
        super().save(*args, **kwargs)

    def clean(self):
        self._normalize_code()
        self._ensure_not_locked()
        self._ensure_base_stays_active()
        super().clean()

    def delete(self, *args, **kwargs):
        if self.is_in_use():
            raise ValidationError(
                "ارزی که در سند استفاده شده قابل حذف نیست؛ آن را غیرفعال کنید."
            )
        super().delete(*args, **kwargs)

    def is_in_use(self):
        """آیا ارز (با کدِ ذخیره‌شده در دیتابیس) در سندی استفاده شده است؟"""
        stored_code = (
            Currency.objects.filter(pk=self.pk).values_list("code", flat=True).first()
        )
        return stored_code is not None and currency_in_use(stored_code)

    def _ensure_not_locked(self):
        if self.pk is None:
            return
        stored = (
            Currency.objects.filter(pk=self.pk).values("code", "decimal_places").first()
        )
        if stored is None or not currency_in_use(stored["code"]):
            return
        errors = {}
        if stored["code"] != self.code:
            errors["code"] = "کد ارزی که در سند استفاده شده قابل تغییر نیست."
        if stored["decimal_places"] != self.decimal_places:
            errors["decimal_places"] = (
                "تعداد اعشار ارزی که در سند استفاده شده قابل تغییر نیست."
            )
        if errors:
            raise ValidationError(errors)

    def _ensure_base_stays_active(self):
        if not self.is_active and self.code == get_base_currency_code():
            raise ValidationError(
                {"is_active": "ارز پایه‌ی فروشگاه را نمی‌شود غیرفعال کرد."}
            )

    def _normalize_code(self):
        self.code = (self.code or "").strip().upper()

    @property
    def quantum(self):
        """کوچک‌ترین واحد این ارز: ۱ یا ۰٫۰۱"""
        return Decimal(10) ** -self.decimal_places

    def round(self, amount):
        """مبلغ را به تعداد اعشار این ارز گرد می‌کند (نیم به بالا)."""
        if isinstance(amount, float):
            raise TypeError("مبلغ را به‌صورت Decimal بدهید، نه float.")
        return Decimal(amount).quantize(self.quantum, rounding=ROUND_HALF_UP)

    def format_amount(self, amount):
        """مبلغ را با جداکننده‌ی هزارگان و اعشار این ارز نشان می‌دهد."""
        return f"{self.round(amount):,.{self.decimal_places}f}"


class Party(TimeStamped):
    """طرف حساب: تأمین‌کننده، مشتری، شریک، فروشنده."""

    name = models.CharField(max_length=200, verbose_name="نام")
    phone = models.CharField(max_length=30, blank=True, verbose_name="تلفن")
    note = models.TextField(blank=True, verbose_name="شرح")

    is_supplier = models.BooleanField(default=False, verbose_name="تامین کننده")
    is_customer = models.BooleanField(default=False, verbose_name="خریدار")
    is_partner = models.BooleanField(default=False, verbose_name="شریک")
    is_seller = models.BooleanField(default=False, verbose_name="فروشنده")
    is_owner = models.BooleanField(default=False, verbose_name="صاحب فروشگاه")
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

    def save(self, *args, **kwargs):
        self._ensure_single_owner()
        super().save(*args, **kwargs)

    def clean(self):
        self._ensure_single_owner()
        super().clean()

    def _ensure_single_owner(self):
        if (
            self.is_owner
            and Party.objects.filter(is_owner=True).exclude(pk=self.pk).exists()
        ):
            raise ValidationError({"is_owner": "فقط یک نفر می‌تواند صاحب فروشگاه باشد."})

    @property
    def can_own(self):
        """آیا می‌تواند در سود یک دستگاه سهم داشته باشد؟"""
        return self.is_owner or self.is_partner


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

    def save(self, *args, **kwargs):
        self._normalize_base_currency()
        self._ensure_single_instance()
        self._ensure_base_currency_unchanged()
        super().save(*args, **kwargs)

    def clean(self):
        self._normalize_base_currency()
        self._ensure_single_instance()
        self._ensure_base_currency_unchanged()
        self._ensure_base_currency_is_available()
        super().clean()

    def _ensure_base_currency_unchanged(self):
        if self.pk is None:
            return
        stored = (
            StoreSettings.objects.filter(pk=self.pk)
            .values_list("base_currency", flat=True)
            .first()
        )
        if stored is None or stored.strip().upper() == self.base_currency:
            return
        if any_documents_exist():
            raise ValidationError(
                {"base_currency": "ارز پایه بعد از ثبت اولین سند قابل تغییر نیست."}
            )

    def _normalize_base_currency(self):
        self.base_currency = (self.base_currency or "").strip().upper()

    def _ensure_single_instance(self):
        if self.pk is None and StoreSettings.objects.exists():
            raise ValidationError("فقط یک فروشگاه می‌توانید در تنظیمات فروشگاه ثبت کنید")

    def _ensure_base_currency_is_available(self):
        available = Currency.objects.filter(
            code=self.base_currency, is_active=True
        ).exists()
        if not available:
            raise ValidationError(
                {"base_currency": "این ارز در فهرست ارزها تعریف نشده یا غیرفعال است."}
            )

    def has_module(self, module_name):
        return module_name in self.enabled_modules

    @classmethod
    def get_solo(cls):
        store = cls.objects.first()
        if store is None:
            store = cls.objects.create(store_name="فروشگاه من")
            Currency.objects.get_or_create(
                code=store.base_currency,
                defaults={"name": "تومان", "decimal_places": 0},
            )
        return store


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

    class Meta:
        ordering = ("-start_date",)
        verbose_name = "دوره"
        verbose_name_plural = "دوره‌ها"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self._ensure_not_closed()
        super().save(*args, **kwargs)

    def clean(self):
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValidationError("تاریخ پایان نمی‌تواند کوچک‌تر از تاریخ شروع باشد")
        self._ensure_not_closed()
        self._ensure_no_overlap()
        super().clean()

    def delete(self, *args, **kwargs):
        self._ensure_not_closed()
        super().delete(*args, **kwargs)

    def close(self, user):
        if self.status == self.Status.CLOSED:
            raise ValidationError("این دوره قبلاً بسته شده است")
        self.status = self.Status.CLOSED
        self.closed_at = timezone.now()
        self.closed_by = user
        self.save(update_fields=["status", "closed_at", "closed_by"])

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

    def _ensure_not_closed(self):
        if (
            self.pk is not None
            and Period.objects.filter(
                pk=self.pk,
                status=self.Status.CLOSED,
            ).exists()
        ):
            raise ValidationError("دوره‌ی بسته‌شده قابل ویرایش یا حذف نیست")

    def _ensure_no_overlap(self):
        if self.start_date is not None and self.end_date is not None:
            overlapping = Period.objects.filter(
                start_date__lte=self.end_date,
                end_date__gte=self.start_date,
            ).exclude(pk=self.pk)
            if overlapping.exists():
                other = overlapping.first()
                raise ValidationError(f"این دوره با دوره «{other}»هم‌پوشانی دارد ")


def get_base_currency_code():
    """کد ارز پایه‌ی فروشگاه (اگر تنظیماتی ثبت نشده باشد IRT)."""
    code = StoreSettings.objects.values_list("base_currency", flat=True).first()
    return (code or "IRT").strip().upper()


def get_base_currency():
    """رکورد ارز پایه در جدول ارزها، یا None اگر تعریف نشده باشد."""
    return Currency.objects.filter(code=get_base_currency_code()).first()


def round_to_base(amount):
    """مبلغ را بر اساس اعشار ارز پایه گرد می‌کند (نیم به بالا)."""
    if isinstance(amount, float):
        raise TypeError("مبلغ را به‌صورت Decimal بدهید، نه float.")
    currency = get_base_currency()
    if currency is None:
        return Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return currency.round(amount)


def format_base(amount):
    """مبلغ پایه را برای نمایش آماده می‌کند."""
    currency = get_base_currency()
    if currency is None:
        return f"{amount:,.2f}"
    return currency.format_amount(amount)


def currency_choices():
    """گزینه‌های فهرست کشویی: ارزهای فعال به شکل (کد، نام نمایشی)."""
    return [(c.code, str(c)) for c in Currency.objects.filter(is_active=True)]


_document_sources = {}


def register_document_source(name, has_documents, uses_currency):
    """هر اپی که سند مالی می‌سازد خودش را اینجا معرفی می‌کند.

    has_documents(): آیا حتی یک سند وجود دارد؟
    uses_currency(code): آیا سندی با این ارز وجود دارد؟
    """
    _document_sources[name] = (has_documents, uses_currency)


def any_documents_exist():
    return any(has_documents() for has_documents, _ in _document_sources.values())


def currency_in_use(code):
    code = (code or "").strip().upper()
    if any(uses(code) for _, uses in _document_sources.values()):
        return True
    return code == get_base_currency_code() and any_documents_exist()
