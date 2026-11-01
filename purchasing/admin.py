from django.contrib import admin

from .models import Purchase, PurchaseLine


class PurchaseLineInline(admin.TabularInline):
    model = PurchaseLine
    extra = 1


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "supplier",
        "invoice_no",
        "currency",
        "status",
        "total",
    )
    list_filter = (
        "status",
        "currency",
    )
    search_fields = (
        "invoice_no",
        "supplier__name",
    )
    inlines = (PurchaseLineInline,)
