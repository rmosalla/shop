from django.contrib import admin

from .models import Unit, UnitOwnership


class UnitOwnershipInline(admin.TabularInline):
    model = UnitOwnership
    extra = 0


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = (
        "uid",
        "variant",
        "serial_number",
        "condition",
        "status",
        "cost_amount",
        "cost_currency",
        "in_stock_since",
    )
    list_filter = ("status", "condition")
    search_fields = ("uid", "serial_number", "variant__sku")
    readonly_fields = ("uid",)
    inlines = (UnitOwnershipInline,)
