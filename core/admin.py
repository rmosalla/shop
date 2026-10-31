from django.contrib import admin, messages
from django.core.exceptions import ValidationError
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
    readonly_fields = (
        "status",
        "closed_at",
        "closed_by",
    )
    actions = ("close_periods",)

    @admin.action(description="بستن دوره‌های انتخاب‌شده")
    def close_periods(self, request, queryset):
        counter = 0
        for period in queryset:
            try:
                period.close(request.user)
                counter += 1
            except ValidationError:
                self.message_user(
                    request, f"دوره «{period.name}» قبلاً بسته شده است.", messages.ERROR
                )
        if counter > 0:
            self.message_user(
                request,
                f"تعداد «{counter}» دوره با موفقیت بسته شد",
            )
        else:
            self.message_user(request, "دوره‌ای برای بستن نبود", messages.ERROR)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.status == Period.Status.CLOSED:
            return False
        return super().has_delete_permission(request, obj)
