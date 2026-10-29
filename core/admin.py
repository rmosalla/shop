from django.contrib import admin
from jalali_suite.admin import JalaliDateModelAdmin

from .models import Party, Period, StoreSettings


@admin.register(Party)
class PartyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "phone",
        "is_supplier",
        "is_customer",
        "is_partner",
        "is_seller",
        "is_active",
    )
    list_filter = ("is_supplier", "is_customer", "is_partner", "is_seller", "is_active")
    search_fields = ("name", "phone")


@admin.register(StoreSettings)
class StoreSettingsAdmin(admin.ModelAdmin):
    list_display = ("store_name", "profit_mode")


@admin.register(Period)
class PeriodAdmin(JalaliDateModelAdmin):
    jalali_widgets_for_gregorian_fields = True
    list_display = ("name", "start_date", "end_date", "status")
