from django.contrib import admin

from .models import Purchase


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "supplier",
        "invoice_no",
        "currency",
        "status",
    )
    list_filter = (
        "status",
        "currency",
    )
    search_fields = (
        "invoice_no",
        "supplier__name",
    )
