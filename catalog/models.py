from django.core.exceptions import ValidationError
from django.db import models

from core.models import TimeStamped


class Category(TimeStamped):
    """مشخصات کالاها"""

    name = models.CharField(max_length=100, verbose_name="نام")
    parent = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )

    class Meta:
        ordering = ("name",)
        verbose_name = "مشخصات کالا"
        verbose_name_plural = "مشخصات کالاها"

    def __str__(self):
        return self.name

    def clean(self):
        if self.pk == self.parent_id:
            raise ValidationError("والد نمی‌تواند با فرزند یکی باشد")
        super().clean()


class Product(TimeStamped):
    """کالا"""

    class Tracking(models.TextChoices):
        SERIALIZED = "serialized", "سریال شده"
        QUANTITY = "quantity", "کمیت"

    category = models.OneToOneField(
        Category,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="category",
    )

    brand = models.CharField(blank=True, max_length=100, verbose_name="برند")
    model_name = models.CharField(max_length=100, verbose_name="مدل")
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
        ordering = ("brand",)
        verbose_name = "کالا"
        verbose_name_plural = "کالاها"

    def __str__(self):
        return (
            f"{self.brand} {self.model_name}".strip() if self.brand else self.model_name
        )
