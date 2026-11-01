from django.apps import AppConfig


class PurchasingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "purchasing"

    def ready(self):
        from core.models import register_document_source

        from .models import Purchase

        def has_documents():
            return Purchase.objects.exists()

        def uses_currency(code):
            return Purchase.objects.filter(currency=code).exists()

        register_document_source("purchasing", has_documents, uses_currency)
