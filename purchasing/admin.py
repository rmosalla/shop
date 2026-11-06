from django import forms
from django.contrib import admin

from core.models import currency_choices, format_base, get_base_currency_code

from .models import Purchase, PurchaseLine, PurchaseLineOwnership


def format_in(amount, currency):
    """مبلغ را با اعشار ارز نشان می‌دهد (اگر ارز تعریف نشده باشد، دو رقم)."""
    if currency is None:
        return f"{amount:,.2f}"
    return currency.format_amount(amount)


class PurchaseAdminForm(forms.ModelForm):
    currency = forms.ChoiceField(label="ارز", choices=())

    class Meta:
        model = Purchase
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "currency" in self.fields:
            self.fields["currency"].choices = currency_choices()
            self.fields["currency"].initial = get_base_currency_code()


class PurchaseLineInline(admin.TabularInline):
    model = PurchaseLine
    extra = 1
    readonly_fields = ("line_total", "line_total_base")

    @admin.display(description="جمع ردیف (ارز فاکتور)")
    def line_total(self, obj):
        if obj.pk is None:
            return "-"
        return format_in(obj.total, obj.purchase.get_currency())

    @admin.display(description="جمع ردیف (ارز پایه)")
    def line_total_base(self, obj):
        if obj.pk is None:
            return "-"
        return format_base(obj.total_base)

    def has_add_permission(self, request, obj=None):
        if obj is not None and not obj.is_draft:
            return False
        return super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if obj is not None and not obj.is_draft:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and not obj.is_draft:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    form = PurchaseAdminForm
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
        return f"{format_in(obj.total, obj.get_currency())} {obj.currency}"

    @admin.display(description="جمع (ارز پایه)")
    def total_base_display(self, obj):
        return format_base(obj.total_base)

    def get_readonly_fields(self, request, obj=None):
        fields_list = [
            "status",
        ]
        if obj is not None and not obj.is_draft:
            fields_list.extend(["supplier", "date", "currency", "exchange_rate"])
        return tuple(fields_list)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and not obj.is_draft:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(PurchaseLineOwnership)
class PurchaseLineOwnershipAdmin(admin.ModelAdmin):
    list_display = ("line", "party", "share_percent")
    search_fields = ("party__name", "line__variant__sku")

    def has_change_permission(self, request, obj=None):
        if obj is not None and not obj.line.purchase.is_draft:
            return False
        else:
            return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and not obj.line.purchase.is_draft:
            return False
        return super().has_delete_permission(request, obj)
