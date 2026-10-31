from django.contrib import admin

from .models import AttributeDefinition, Category, Product, Variant


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "parent",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "parent__name")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "model_name",
        "category",
        "brand",
        "part_number",
        "tracking_type",
        "warranty_months",
        "is_active",
    )
    list_filter = ("tracking_type", "category", "is_active")
    search_fields = ("model_name", "category__name", "brand", "part_number")


@admin.register(Variant)
class VariantAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "sku",
        "default_price_base",
        "is_active",
    )
    search_fields = (
        "sku",
        "product__model_name",
    )
    list_filter = ("is_active",)


@admin.register(AttributeDefinition)
class AttributeDefinitionAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "key",
        "value_type",
        "unit",
        "is_active",
    )
    list_filter = (
        "value_type",
        "is_active",
    )
    search_fields = (
        "key",
        "label",
    )
