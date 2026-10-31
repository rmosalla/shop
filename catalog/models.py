from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from core.models import TimeStamped


class Category(TimeStamped):
    """دسته‌بندی کالا‌ها"""

    name = models.CharField(max_length=100, unique=True, verbose_name="نام")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
        verbose_name="دسته‌ی والد",
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        ordering = ("name",)
        verbose_name = "دسته‌بندی کالا"
        verbose_name_plural = "دسته‌بندی کالاها"

    def __str__(self):
        return self.name

    def clean(self):
        if self.pk is not None and self.pk == self.parent_id:
            raise ValidationError("یک دسته نمی‌تواند والد خودش باشد")
        super().clean()


class Product(TimeStamped):
    """کالا"""

    class Tracking(models.TextChoices):
        SERIALIZED = "serialized", "سریال شده"
        QUANTITY = "quantity", "کمیت"

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name="دسته‌بندی",
    )

    brand = models.CharField(blank=True, max_length=100, verbose_name="برند")
    model_name = models.CharField(max_length=200, verbose_name="مدل")
    part_number = models.CharField(
        blank=True, db_index=True, max_length=100, verbose_name="پارت نامبر"
    )
    tracking_type = models.CharField(
        max_length=10,
        choices=Tracking.choices,
        default=Tracking.SERIALIZED,
        verbose_name="نوع ردیابی",
    )
    warranty_months = models.PositiveSmallIntegerField(
        default=0, verbose_name="گارانتی"
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        ordering = (
            "brand",
            "model_name",
        )
        verbose_name = "کالا"
        verbose_name_plural = "کالاها"

    def __str__(self):
        return f"{self.brand} {self.model_name}" if self.brand else self.model_name


class Variant(TimeStamped):
    """کانفیگ"""

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="variants",
        verbose_name="کالا",
    )
    sku = models.CharField(max_length=80, unique=True, verbose_name="کد یکتا")
    attributes = models.JSONField(default=dict, blank=True, verbose_name="مشخصات")
    default_price_base = models.DecimalField(
        max_digits=18,
        decimal_places=3,
        default=0,
        verbose_name="قیمت",
        validators=[MinValueValidator(0)],
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        ordering = (
            "product",
            "sku",
        )
        verbose_name = "کانفیگ"
        verbose_name_plural = "کانفیگ‌ها"

    def __str__(self):
        return self.sku
