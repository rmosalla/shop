from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils.text import slugify

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

    def lineage_ids(self):
        """شناسه‌ی این دسته و همه‌ی والدهایش تا ریشه."""
        ids = set()
        current = self
        while current is not None and current.pk not in ids:
            ids.add(current.pk)
            current = current.parent
        return ids

    def clean(self):
        parent = self.parent
        if self.pk is not None and parent is not None:
            if self.pk in parent.lineage_ids():
                raise ValidationError(
                    {
                        "parent": (
                            "دسته‌ی والد نمی‌تواند خود دسته یا یکی از زیردسته‌هایش باشد"
                        )
                    }
                )
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
    sku = models.CharField(
        max_length=80,
        unique=True,
        blank=True,
        editable=False,
        verbose_name="کد یکتا",
        help_text="خودکار از روی کالا و مشخصات ساخته می‌شود",
    )
    attributes = models.JSONField(default=dict, blank=True, verbose_name="مشخصات")
    attributes_key = models.CharField(
        max_length=500, default="", blank=True, editable=False, verbose_name="کد مشخصات"
    )
    default_price_base = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
        verbose_name="قیمت فروش",
        help_text="قیمت فروش جاری این کانفیگ. صفر یعنی هنوز قیمت‌گذاری نشده.",
        validators=[MinValueValidator(0)],
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        ordering = (
            "product",
            "sku",
        )
        constraints = (
            models.UniqueConstraint(
                fields=("product", "attributes_key"),
                name="uniq_variant_product_attributes",
            ),
        )
        verbose_name = "کانفیگ"
        verbose_name_plural = "کانفیگ‌ها"

    def __str__(self):
        return self.sku

    def save(self, *args, **kwargs):
        self._ensure_not_locked()
        self.attributes_key = self._build_attributes_key()
        if self.has_documents():
            self.sku = Variant.objects.values_list("sku", flat=True).get(pk=self.pk)
        else:
            self.sku = self._generate_sku()
        super().save(*args, **kwargs)

    def clean(self):
        if not isinstance(self.attributes, dict):
            raise ValidationError(
                {"attributes": "این فیلد باید یک دیکشنری (dict) باشد."}
            )
        self._ensure_not_locked()
        self._validate_attributes()
        self.attributes_key = self._build_attributes_key()
        if self.product_id is not None:
            duplicates = Variant.objects.filter(
                product_id=self.product_id,
                attributes_key=self.attributes_key,
            ).exclude(pk=self.pk)
            if duplicates.exists():
                raise ValidationError("این مدل با این مشخصات قبلاً ثبت شده است")
        super().clean()

    def has_documents(self):
        """آیا هیچ سندی (خرید، فروش و...) به این کانفیگ وصل شده است؟"""
        if self.pk is None:
            return False
        for relation in self._meta.related_objects:
            if relation.one_to_many:
                if getattr(self, relation.get_accessor_name()).exists():
                    return True
        return False

    def _ensure_not_locked(self):
        if not self.has_documents():
            return
        stored = (
            Variant.objects.filter(pk=self.pk)
            .values("product_id", "attributes")
            .first()
        )
        errors = {}
        if stored["product_id"] != self.product_id:
            errors["product"] = "کالای یک کانفیگ دارای سند قابل تغییر نیست"
        if stored["attributes"] != self.attributes:
            errors["attributes"] = (
                "مشخصات کانفیگ دارای سند قابل تغییر نیست؛ کانفیگ جدید بسازید"
            )
        if errors:
            raise ValidationError(errors)

    def _validate_attributes(self):
        types = AttributeDefinition.ValueType
        category = self.product.category if self.product_id is not None else None
        definitions = {
            d.key: d
            for d in AttributeDefinition.objects.filter(
                key__in=self.attributes.keys(), is_active=True
            )
        }
        errors = []
        for key, value in self.attributes.items():
            definition = definitions.get(key)
            if definition is None:
                errors.append(f"مشخصه‌ی «{key}» تعریف نشده یا غیرفعال است.")
                continue
            label = definition.label
            if not definition.applies_to(category):
                errors.append(f"مشخصه‌ی «{label}» برای این دسته‌بندی مجاز نیست.")
                continue
            if definition.value_type == types.NUMBER:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    errors.append(f"مقدار «{label}» باید عدد باشد.")
            elif definition.value_type == types.TEXT:
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"مقدار «{label}» باید متنِ غیرخالی باشد.")
            elif definition.value_type == types.CHOICE:
                if value not in definition.choices:
                    options = "، ".join(definition.choices)
                    errors.append(f"مقدار «{label}» باید یکی از این‌ها باشد: {options}")
        if errors:
            raise ValidationError({"attributes": errors})

    def _build_attributes_key(self):
        parts = []
        for key, value in sorted(self.attributes.items()):
            parts.append(f"{key}={value}")
        return "|".join(parts)

    def _generate_sku(self):
        ordered = sorted(
            self.attributes.items(), key=lambda item: (item[0] == "other", item[0])
        )
        raw = [self.product.brand, self.product.model_name]
        raw += [str(value).replace(".", "_") for _key, value in ordered]
        parts = [slug for slug in (slugify(item) for item in raw) if slug]
        base = "-".join(parts).upper()[:70] or f"P{self.product_id}"
        candidate = base
        number = 2
        while Variant.objects.filter(sku=candidate).exclude(pk=self.pk).exists():
            candidate = f"{base}-{number}"
            number += 1
        return candidate


class AttributeDefinition(TimeStamped):
    """تعریف مشخصه‌های قابل استفاده در کانفیگ (مثل رم و SSD)"""

    class ValueType(models.TextChoices):
        TEXT = "text", "متن"
        NUMBER = "number", "عدد"
        CHOICE = "choice", "انتخابی"

    key = models.CharField(
        max_length=50,
        unique=True,
        validators=[
            RegexValidator(
                regex=r"^[a-z][a-z0-9_]*$",
                message=(
                    "کلید باید با یک حرف کوچک انگلیسی شروع شود "
                    "و فقط شامل حروف کوچک انگلیسی، اعداد و زیرخط باشد."
                ),
                code="invalid_key",
            )
        ],
        verbose_name="کلید",
    )
    label = models.CharField(max_length=100, verbose_name="نام نمایشی")
    value_type = models.CharField(
        max_length=10,
        choices=ValueType.choices,
        verbose_name="نوع مقدار",
        default=ValueType.TEXT,
    )
    choices = models.JSONField(default=list, blank=True, verbose_name="گزینه‌ها")
    unit = models.CharField(max_length=20, blank=True, verbose_name="واحد")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    categories = models.ManyToManyField(
        Category,
        blank=True,
        related_name="attribute_definitions",
        verbose_name="دسته‌بندی‌های مجاز",
        help_text="اگر خالی بماند، برای همه‌ی دسته‌بندی‌ها مجاز است",
    )

    class Meta:
        ordering = ("label",)
        verbose_name = "مشخصه"
        verbose_name_plural = "مشخصه‌ها"

    def __str__(self):
        return self.label

    def clean(self):
        if self.value_type == self.ValueType.CHOICE:
            if (
                not isinstance(self.choices, list)
                or not self.choices
                or not all(isinstance(item, str) for item in self.choices)
            ):
                raise ValidationError(
                    {"choices": "گزینه‌ها باید فهرستی غیرخالی از متن باشند"}
                )
        elif self.choices:
            raise ValidationError({"choices": "این نوع گزینه نمی‌خواهد"})
        super().clean()

    def applies_to(self, category):
        """آیا این مشخصه برای این دسته (یا والدهایش) مجاز است؟"""
        allowed = set(self.categories.values_list("pk", flat=True))
        if not allowed or category is None:
            return True
        return bool(allowed & category.lineage_ids())
