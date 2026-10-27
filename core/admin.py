from django.contrib import admin
from .models import Party

@admin.register(Party)
class PartyAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "is_supplier", "is_customer", "is_partner", "is_seller", "is_active")
    list_filter = ("is_supplier", "is_customer", "is_partner", "is_seller", "is_active")
    search_fields = ("name", "phone")