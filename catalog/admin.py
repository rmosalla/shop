from django.contrib import admin

from .models import Category, Product


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
