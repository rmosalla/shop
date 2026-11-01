from django.contrib import admin

from .models import Purchase, PurchaseLine


class PurchaseLineInline(admin.TabularInline):
    model = PurchaseLine
    extra = 1
    readonly_fields = ("line_total", "line_total_base")

    @admin.display(description="جمع ردیف (ارز فاکتور)")
    def line_total(self, obj):
        if obj.pk is None:
            return "-"
        return f"{obj.total:,.2f}"

    @admin.display(description="جمع ردیف (ارز پایه)")
    def line_total_base(self, obj):
        if obj.pk is None:
            return "-"
        return f"{obj.total_base:,.2f}"


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "supplier",
        "invoice_no",
        "currency",
        "exchange_rate",
        "status",
        "total_display",
        "total_base_display",
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

    @admin.display(description="جمع (ارز فاکتور)")
    def total_display(self, obj):
        return f"{obj.total:,.2f} {obj.currency}"

    @admin.display(description="جمع (ارز پایه)")
    def total_base_display(self, obj):
        return f"{obj.total_base:,.2f}"
