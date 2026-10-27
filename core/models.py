
from django.conf import settings
from django.db import models


class TimeStamped(models.Model):
    """فیلدهای مشترک همه‌ی مدل‌ها."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Party(TimeStamped):
    """طرف حساب: تأمین‌کننده، مشتری، شریک، فروشنده."""
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30, blank=True)
    note = models.TextField(blank=True)

    is_supplier = models.BooleanField(default=False)
    is_customer = models.BooleanField(default=False)
    is_partner = models.BooleanField(default=False)
    is_seller = models.BooleanField(default=False)

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="party",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name