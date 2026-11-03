from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction

from catalog.models import Product, Variant
from core.models import Party, TimeStamped
from purchasing.models import PurchaseLine


class Unit(TimeStamped):
    """یک دستگاه فیزیکی (فقط برای کالای سریال‌دار)."""

    class Condition(models.TextChoices):
        NEW = "new", "نو"
        OPEN_BOX = "open_box", "آکبند/اوپن‌باکس"
        USED = "used", "استوک"

    class Grade(models.TextChoices):
        A = "A", "A"
        B = "B", "B"
        C = "C", "C"

    class Status(models.TextChoices):
        IN_STOCK = "in_stock", "موجود"
        RESERVED = "reserved", "رزرو"
        SOLD = "sold", "فروخته‌شده"
        WRITTEN_OFF = "written_off", "خارج‌شده"

    uid = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        editable=False,
        verbose_name="کد دستگاه",
    )
    variant = models.ForeignKey(
        Variant,
        on_delete=models.PROTECT,
        related_name="units",
        verbose_name="کانفیگ",
    )
    purchase_line = models.ForeignKey(
        PurchaseLine,
        on_delete=models.PROTECT,
        related_name="units",
        verbose_name="ردیف فاکتور خرید",
    )
    serial_number = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        verbose_name="سریال",
    )
    condition = models.CharField(
        max_length=10,
        choices=Condition.choices,
        default=Condition.NEW,
        verbose_name="وضعیت ظاهری",
    )
    grade = models.CharField(
        max_length=1,
        choices=Grade.choices,
        blank=True,
        verbose_name="گرید",
    )
    battery_health = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MaxValueValidator(100)],
        verbose_name="سلامت باتری (٪)",
    )
    note = models.TextField(blank=True, verbose_name="یادداشت")
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.IN_STOCK,
        db_index=True,
        verbose_name="وضعیت",
    )
    cost_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="بهای خرید (ارز فاکتور)",
    )
    cost_currency = models.CharField(max_length=5, verbose_name="ارز بهای خرید")
    cost_rate = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=1,
        validators=[MinValueValidator(Decimal("0.0001"))],
        verbose_name="نرخ ارز هنگام خرید",
    )
    cost_base = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="بهای خرید (ارز پایه)",
    )
    asking_price_base = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="قیمت فروش اختصاصی",
        help_text="اگر خالی باشد، قیمت فروش کانفیگ استفاده می‌شود.",
    )
    in_stock_since = models.DateField(verbose_name="تاریخ ورود به انبار")

    class Meta:
        ordering = ("-in_stock_since", "-id")
        verbose_name = "دستگاه"
        verbose_name_plural = "دستگاه‌ها"

    def __str__(self):
        return self.uid or "دستگاه جدید"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            self.uid = (
                Unit.objects.filter(pk=self.pk).values_list("uid", flat=True).first()
            )
            super().save(*args, **kwargs)
            return
        with transaction.atomic():
            super().save(*args, **kwargs)
            self.uid = f"U{self.pk:06d}"
            Unit.objects.filter(pk=self.pk).update(uid=self.uid)

    def clean(self):
        if self.variant_id is not None:
            tracking = self.variant.product.tracking_type
            if tracking != Product.Tracking.SERIALIZED:
                raise ValidationError(
                    {"variant": "فقط کالای سریال‌دار دستگاه جداگانه می‌گیرد."}
                )
            if (
                self.purchase_line_id is not None
                and self.variant_id != self.purchase_line.variant_id
            ):
                raise ValidationError(
                    {"variant": "کانفیگ دستگاه با ردیف فاکتور خرید هم‌خوان نیست."}
                )
        super().clean()

    @property
    def effective_price_base(self):
        """قیمت فروش جاری: اختصاصی اگر بود، وگرنه قیمت کانفیگ."""
        if self.asking_price_base is not None:
            return self.asking_price_base
        return self.variant.default_price_base

    @property
    def ownership_total(self):
        """مجموع سهم‌های ثبت‌شده برای این دستگاه (باید ۱۰۰ باشد)."""
        return sum((row.share_percent for row in self.ownerships.all()), Decimal("0"))


class UnitOwnership(TimeStamped):
    """سهم یک شخص از یک دستگاه مشخص."""

    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name="ownerships",
        verbose_name="دستگاه",
    )
    party = models.ForeignKey(
        Party,
        on_delete=models.PROTECT,
        related_name="unit_ownerships",
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
                fields=("unit", "party"), name="uniq_unit_ownership_party"
            ),
        )
        verbose_name = "سهم دستگاه"
        verbose_name_plural = "سهم‌های دستگاه"

    def __str__(self):
        return f"{self.party.name}: {self.share_percent}%"

    def clean(self):
        if self.party_id is not None and not self.party.can_own:
            raise ValidationError(
                {"party": "فقط صاحب فروشگاه یا شریک می‌تواند سهم داشته باشد."}
            )
        super().clean()
