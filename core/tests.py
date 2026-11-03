from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import (
    Currency,
    Party,
    Period,
    StoreSettings,
    any_documents_exist,
    currency_choices,
    currency_in_use,
    format_base,
    get_base_currency,
    get_base_currency_code,
    register_document_source,
    round_to_base,
)

User = get_user_model()


class PartyTests(TestCase):
    def test_str_returns_name(self):
        p = Party.objects.create(name="علی")
        self.assertEqual(str(p), "علی")

    def test_roles_default_to_false(self):
        p = Party.objects.create(name="x")
        self.assertFalse(p.is_supplier or p.is_customer or p.is_partner or p.is_seller)


class StoreSettingsTests(TestCase):
    def test_defaults_are_set(self):
        s = StoreSettings.objects.create(store_name="Test Store")
        self.assertEqual(s.base_currency, "IRT")
        self.assertEqual(s.profit_mode, "base")
        self.assertEqual(s.costing_method, "wavg")

    def test_str_returns_name(self):
        s = StoreSettings.objects.create(store_name="Test Store")
        self.assertEqual(str(s), "Test Store")

    def test_enabled_modules_is_empty(self):
        s = StoreSettings.objects.create(store_name="Test Store")
        self.assertEqual(s.enabled_modules, [])

    def test_second_instance_is_rejected(self):
        StoreSettings.objects.create(store_name="Test Store1")
        with self.assertRaises(ValidationError):
            StoreSettings.objects.create(store_name="Test Store2")
        self.assertEqual(StoreSettings.objects.count(), 1)

    def test_changing_store_name_does_not_raise(self):
        s = StoreSettings.objects.create(store_name="Test Store")
        s.store_name = "Changed Name"
        s.save()
        s.refresh_from_db()
        self.assertEqual(s.store_name, "Changed Name")

    def test_clean_rejects_second_instance(self):
        StoreSettings.objects.create(store_name="Test Store")
        second = StoreSettings(store_name="Test Store2")
        with self.assertRaises(ValidationError):
            second.full_clean()

    def test_clean_allows_existing_instance(self):
        Currency.objects.create(code="IRT", name="تومان", decimal_places=0)
        s = StoreSettings.objects.create(store_name="Test Store")
        s.full_clean()

    def test_has_module_true_when_enabled(self):
        s = StoreSettings.objects.create(
            store_name="Test Store",
            enabled_modules=["currency"],
        )
        self.assertTrue(s.has_module("currency"))

    def test_has_module_false_when_not_enabled(self):
        s = StoreSettings.objects.create(
            store_name="Test Store",
            enabled_modules=["currency"],
        )
        self.assertFalse(s.has_module("installments"))

    def test_has_module_false_when_empty(self):
        s = StoreSettings.objects.create(
            store_name="Test Store",
        )
        self.assertFalse(s.has_module("installments"))

    def test_get_solo_creates_settings_when_missing(self):
        self.assertEqual(StoreSettings.objects.count(), 0)
        StoreSettings.get_solo()
        self.assertEqual(StoreSettings.objects.count(), 1)

    def test_get_solo_returns_existing_settings(self):
        existing = StoreSettings.objects.create(store_name="Test Store")
        found = StoreSettings.get_solo()
        self.assertEqual(found.pk, existing.pk)
        self.assertEqual(StoreSettings.objects.count(), 1)

    def test_unknown_base_currency_rejected(self):
        s = StoreSettings(store_name="S", base_currency="XYZ")
        with self.assertRaises(ValidationError):
            s.full_clean()

    def test_inactive_base_currency_rejected(self):
        Currency.objects.create(
            code="IRT", name="تومان", decimal_places=0, is_active=False
        )
        with self.assertRaises(ValidationError):
            StoreSettings(store_name="S").full_clean()

    def test_known_base_currency_accepted(self):
        Currency.objects.create(code="IRT", name="تومان", decimal_places=0)
        StoreSettings(store_name="S").full_clean()

    def test_lowercase_base_currency_is_normalized_in_clean(self):
        Currency.objects.create(code="USD", name="دلار")
        s = StoreSettings(store_name="S", base_currency="usd")
        s.full_clean()
        self.assertEqual(s.base_currency, "USD")

    def test_base_currency_is_stored_uppercase(self):
        s = StoreSettings.objects.create(store_name="S", base_currency="iqd")
        s.refresh_from_db()
        self.assertEqual(s.base_currency, "IQD")

    def test_get_solo_creates_default_currency(self):
        StoreSettings.get_solo()
        irt = Currency.objects.get(code="IRT")
        self.assertEqual(irt.decimal_places, 0)

    def test_get_solo_keeps_existing_currency_settings(self):
        Currency.objects.create(code="IRT", name="ریال", decimal_places=2)
        StoreSettings.get_solo()
        self.assertEqual(Currency.objects.filter(code="IRT").count(), 1)
        self.assertEqual(Currency.objects.get(code="IRT").decimal_places, 2)


class PeriodTests(TestCase):
    def test_reject_reversed_dates(self):
        p = Period(
            name="october", start_date=date(2026, 10, 30), end_date=date(2026, 10, 1)
        )
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_valid_period_is_accepted(self):
        p = Period(
            name="october", start_date=date(2026, 10, 1), end_date=date(2026, 10, 30)
        )
        p.full_clean()

    def test_add_one_day_period_accepted(self):
        p = Period(
            name="one day", start_date=date(2026, 10, 1), end_date=date(2026, 10, 1)
        )
        p.full_clean()

    def test_reject_date_in_closed_period(self):
        Period.objects.create(
            name="october",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 30),
            status=Period.Status.CLOSED,
        )
        with self.assertRaises(ValidationError):
            Period.assert_date_open(date(2026, 10, 5))

    def test_date_in_open_period_accepted(self):
        Period.objects.create(
            name="october",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 30),
        )
        Period.assert_date_open(date(2026, 10, 5))

    def test_date_with_no_periods_is_accepted(self):
        Period.assert_date_open(date(2026, 10, 5))

    def test_date_equal_to_closed_period_start_date_rejected(self):
        Period.objects.create(
            name="october",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 30),
            status=Period.Status.CLOSED,
        )
        with self.assertRaises(ValidationError):
            Period.assert_date_open(date(2026, 10, 1))

    def test_date_equal_to_closed_period_end_date_rejected(self):
        Period.objects.create(
            name="october",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 30),
            status=Period.Status.CLOSED,
        )
        with self.assertRaises(ValidationError):
            Period.assert_date_open(date(2026, 10, 30))

    def test_date_out_of_closed_period_accepted(self):
        Period.objects.create(
            name="october",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 30),
            status=Period.Status.CLOSED,
        )
        Period.assert_date_open(date(2026, 11, 1))

    def test_add_period_without_startdate_or_enddate_reject(self):
        p = Period(name="No date")
        with self.assertRaises(ValidationError):
            p.full_clean()


class PeriodCloseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="admin", password="pass12345")
        self.period = Period.objects.create(
            name="october",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 30),
        )

    def test_close_sets_status_closed(self):
        self.assertEqual(self.period.status, Period.Status.OPEN)
        self.period.close(self.user)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, Period.Status.CLOSED)

    def test_close_period_closed_by_logined_user(self):
        self.period.close(self.user)
        self.period.refresh_from_db()
        self.assertEqual(self.period.closed_by, self.user)

    def test_close_period_closed_at_not_none(self):
        self.period.close(self.user)
        self.period.refresh_from_db()
        self.assertIsNotNone(self.period.closed_at)

    def test_close_closed_period_rejected(self):
        self.period.close(self.user)
        with self.assertRaises(ValidationError):
            self.period.close(self.user)

    def test_edit_closed_period_rejected(self):
        self.period.close(self.user)
        self.period.end_date = date(2026, 10, 15)
        with self.assertRaises(ValidationError):
            self.period.save()

    def test_edit_open_period_accepted(self):
        self.period.end_date = date(2026, 10, 15)
        self.period.save()
        self.period.refresh_from_db()
        self.assertEqual(self.period.end_date, date(2026, 10, 15))

    def test_clean_edit_closed_period_rejected(self):
        self.period.close(self.user)
        with self.assertRaises(ValidationError):
            self.period.full_clean()

    def test_delete_closed_period_rejected(self):
        self.period.close(self.user)
        with self.assertRaises(ValidationError):
            self.period.delete()
        self.assertEqual(Period.objects.count(), 1)

    def test_delete_open_period_accepted(self):
        self.period.delete()
        self.assertEqual(Period.objects.count(), 0)


class PeriodOverlapTests(TestCase):
    def setUp(self):
        self.october = Period.objects.create(
            name="october",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 30),
        )

    def test_partial_overlap_rejected(self):
        p = Period(
            name="overlap",
            start_date=date(2026, 10, 15),
            end_date=date(2026, 11, 15),
        )
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_period_inside_another_rejected(self):
        p = Period(
            name="inside",
            start_date=date(2026, 10, 10),
            end_date=date(2026, 10, 20),
        )
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_period_containing_another_rejected(self):
        p = Period(
            name="wide",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 11, 30),
        )
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_sharing_one_day_rejected(self):
        p = Period(
            name="shared day",
            start_date=date(2026, 10, 30),
            end_date=date(2026, 11, 30),
        )
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_adjacent_period_accepted(self):
        p = Period(
            name="november",
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 30),
        )
        p.full_clean()

    def test_editing_same_period_accepted(self):
        self.october.name = "renamed"
        self.october.full_clean()


class CurrencyTests(TestCase):
    def test_defaults(self):
        c = Currency.objects.create(code="USD", name="دلار")
        self.assertEqual(c.decimal_places, 2)
        self.assertTrue(c.is_active)
        self.assertEqual(c.symbol, "")

    def test_str(self):
        c = Currency.objects.create(code="USD", name="دلار")
        self.assertEqual(str(c), "دلار (USD)")

    def test_code_is_stored_uppercase(self):
        c = Currency.objects.create(code="usd", name="دلار")
        c.refresh_from_db()
        self.assertEqual(c.code, "USD")

    def test_full_clean_normalizes_lowercase_code(self):
        c = Currency(code="usd", name="دلار")
        c.full_clean()
        self.assertEqual(c.code, "USD")

    def test_duplicate_code_rejected_ignoring_case(self):
        Currency.objects.create(code="USD", name="دلار")
        second = Currency(code="usd", name="دلار دوم")
        with self.assertRaises(ValidationError):
            second.full_clean()

    def test_invalid_codes_rejected(self):
        for code in ["US", "USDT", "12A", "US$", "دلا", ""]:
            with self.subTest(code=code):
                with self.assertRaises(ValidationError):
                    Currency(code=code, name="x").full_clean()

    def test_decimal_places_out_of_range_rejected(self):
        for places in [-1, 3]:
            with self.subTest(places=places):
                with self.assertRaises(ValidationError):
                    Currency(code="USD", name="x", decimal_places=places).full_clean()

    def test_valid_decimal_places_accepted(self):
        for places in [0, 1, 2]:
            with self.subTest(places=places):
                Currency(code="USD", name="x", decimal_places=places).full_clean()


class CurrencyRoundingTests(TestCase):
    def setUp(self):
        self.toman = Currency.objects.create(code="IRT", name="تومان", decimal_places=0)
        self.dollar = Currency.objects.create(code="USD", name="دلار")

    def test_quantum(self):
        self.assertEqual(self.toman.quantum, Decimal("1"))
        self.assertEqual(self.dollar.quantum, Decimal("0.01"))

    def test_zero_decimals_rounds_half_up(self):
        self.assertEqual(self.toman.round(Decimal("1500.5")), Decimal("1501"))
        self.assertEqual(self.toman.round(Decimal("1500.4")), Decimal("1500"))

    def test_two_decimals_rounds_half_up(self):
        self.assertEqual(self.dollar.round(Decimal("10.125")), Decimal("10.13"))
        self.assertEqual(self.dollar.round(Decimal("10.124")), Decimal("10.12"))

    def test_negative_half_rounds_away_from_zero(self):
        self.assertEqual(self.toman.round(Decimal("-1500.5")), Decimal("-1501"))

    def test_result_has_the_currency_exponent(self):
        self.assertEqual(self.toman.round(Decimal("5")).as_tuple().exponent, 0)
        self.assertEqual(self.dollar.round(Decimal("5")).as_tuple().exponent, -2)

    def test_integer_input_accepted(self):
        self.assertEqual(self.dollar.round(5), Decimal("5.00"))

    def test_float_input_rejected(self):
        with self.assertRaises(TypeError):
            self.dollar.round(5.1)


class CurrencyFormatTests(TestCase):
    def setUp(self):
        self.toman = Currency.objects.create(code="IRT", name="تومان", decimal_places=0)
        self.dollar = Currency.objects.create(code="USD", name="دلار")

    def test_zero_decimals_shows_no_fraction(self):
        text = self.toman.format_amount(Decimal("1500000.00"))
        self.assertEqual(text, "1,500,000")

    def test_two_decimals_always_shows_two(self):
        self.assertEqual(self.dollar.format_amount(Decimal("1250.5")), "1,250.50")
        self.assertEqual(self.dollar.format_amount(Decimal("1250")), "1,250.00")

    def test_small_numbers_and_zero(self):
        self.assertEqual(self.toman.format_amount(Decimal("0")), "0")
        self.assertEqual(self.toman.format_amount(Decimal("999")), "999")

    def test_negative_number(self):
        text = self.toman.format_amount(Decimal("-1234567"))
        self.assertEqual(text, "-1,234,567")

    def test_rounds_before_formatting(self):
        self.assertEqual(self.toman.format_amount(Decimal("1500.5")), "1,501")


class BaseCurrencyHelpersTests(TestCase):
    def test_code_defaults_to_irt_without_settings(self):
        self.assertEqual(get_base_currency_code(), "IRT")

    def test_code_comes_from_store_settings_in_uppercase(self):
        StoreSettings.objects.create(store_name="S", base_currency="iqd")
        self.assertEqual(get_base_currency_code(), "IQD")

    def test_base_currency_is_none_when_not_defined(self):
        self.assertIsNone(get_base_currency())

    def test_base_currency_returns_the_record(self):
        toman = Currency.objects.create(code="IRT", name="تومان", decimal_places=0)
        self.assertEqual(get_base_currency(), toman)

    def test_round_to_base_uses_currency_decimals(self):
        Currency.objects.create(code="IRT", name="تومان", decimal_places=0)
        self.assertEqual(round_to_base(Decimal("1.5")), Decimal("2"))
        self.assertEqual(round_to_base(Decimal("1.4")), Decimal("1"))

    def test_round_to_base_falls_back_to_two_decimals(self):
        self.assertEqual(round_to_base(Decimal("0.125")), Decimal("0.13"))

    def test_round_to_base_rejects_float(self):
        with self.assertRaises(TypeError):
            round_to_base(1.5)

    def test_format_base_with_currency(self):
        Currency.objects.create(code="IRT", name="تومان", decimal_places=0)
        self.assertEqual(format_base(Decimal("1500000")), "1,500,000")

    def test_format_base_falls_back_to_two_decimals(self):
        self.assertEqual(format_base(Decimal("1500000")), "1,500,000.00")


class CurrencyChoicesTests(TestCase):
    def test_only_active_currencies_are_offered(self):
        Currency.objects.create(code="USD", name="دلار")
        Currency.objects.create(code="EUR", name="یورو", is_active=False)
        codes = [code for code, _label in currency_choices()]
        self.assertEqual(codes, ["USD"])

    def test_choice_label_contains_name_and_code(self):
        Currency.objects.create(code="USD", name="دلار")
        self.assertEqual(currency_choices(), [("USD", "دلار (USD)")])


def sources(has_documents=False, used_codes=()):
    """منبع ساختگی سند، برای آزمایش قفل‌ها بدون وابستگی به اپ‌های دیگر."""
    return {"fake": (lambda: has_documents, lambda code: code in used_codes)}


class DocumentRegistryTests(TestCase):
    def test_no_sources_means_no_documents(self):
        with patch("core.models._document_sources", {}):
            self.assertFalse(any_documents_exist())
            self.assertFalse(currency_in_use("USD"))

    def test_registered_source_is_consulted(self):
        with patch("core.models._document_sources", {}):
            register_document_source("x", lambda: True, lambda code: False)
            self.assertTrue(any_documents_exist())

    def test_registering_same_name_twice_keeps_one_source(self):
        with patch("core.models._document_sources", {}) as registry:
            register_document_source("x", lambda: False, lambda code: False)
            register_document_source("x", lambda: True, lambda code: False)
            self.assertEqual(len(registry), 1)
            self.assertTrue(any_documents_exist())

    def test_currency_in_use_by_a_source(self):
        registry = sources(used_codes=("USD",))
        with patch("core.models._document_sources", registry):
            self.assertTrue(currency_in_use("USD"))
            self.assertFalse(currency_in_use("EUR"))

    def test_currency_check_ignores_case(self):
        registry = sources(used_codes=("USD",))
        with patch("core.models._document_sources", registry):
            self.assertTrue(currency_in_use("usd"))

    def test_base_currency_is_in_use_when_any_document_exists(self):
        registry = sources(has_documents=True)
        with patch("core.models._document_sources", registry):
            self.assertTrue(currency_in_use("IRT"))
            self.assertFalse(currency_in_use("USD"))


class CurrencyLockTests(TestCase):
    def setUp(self):
        self.usd = Currency.objects.create(code="USD", name="دلار")
        self.irt = Currency.objects.create(code="IRT", name="تومان", decimal_places=0)

    def used(self):
        return patch("core.models._document_sources", sources(used_codes=("USD",)))

    def unused(self):
        return patch("core.models._document_sources", sources())

    def test_unused_currency_can_change_decimals(self):
        with self.unused():
            self.usd.decimal_places = 0
            self.usd.save()
        self.usd.refresh_from_db()
        self.assertEqual(self.usd.decimal_places, 0)

    def test_unused_currency_can_change_code(self):
        with self.unused():
            self.usd.code = "EUR"
            self.usd.save()
        self.usd.refresh_from_db()
        self.assertEqual(self.usd.code, "EUR")

    def test_used_currency_decimals_cannot_change_on_save(self):
        with self.used():
            self.usd.decimal_places = 0
            with self.assertRaises(ValidationError):
                self.usd.save()
        self.usd.refresh_from_db()
        self.assertEqual(self.usd.decimal_places, 2)

    def test_used_currency_decimals_cannot_change_in_clean(self):
        with self.used():
            self.usd.decimal_places = 0
            with self.assertRaises(ValidationError):
                self.usd.full_clean()

    def test_used_currency_code_cannot_change(self):
        with self.used():
            self.usd.code = "EUR"
            with self.assertRaises(ValidationError):
                self.usd.save()
        self.usd.refresh_from_db()
        self.assertEqual(self.usd.code, "USD")

    def test_used_currency_name_and_symbol_can_change(self):
        with self.used():
            self.usd.name = "دلار آمریکا"
            self.usd.symbol = "$"
            self.usd.save()
        self.usd.refresh_from_db()
        self.assertEqual(self.usd.name, "دلار آمریکا")
        self.assertEqual(self.usd.symbol, "$")

    def test_used_currency_can_be_deactivated(self):
        with self.used():
            self.usd.is_active = False
            self.usd.save()
        self.usd.refresh_from_db()
        self.assertFalse(self.usd.is_active)

    def test_used_currency_unchanged_passes_full_clean(self):
        with self.used():
            self.usd.full_clean()

    def test_unused_currency_can_be_deleted(self):
        with self.unused():
            self.usd.delete()
        self.assertFalse(Currency.objects.filter(code="USD").exists())

    def test_used_currency_cannot_be_deleted(self):
        with self.used():
            with self.assertRaises(ValidationError):
                self.usd.delete()
        self.assertTrue(Currency.objects.filter(code="USD").exists())

    def test_base_currency_decimals_locked_when_any_document_exists(self):
        with patch("core.models._document_sources", sources(has_documents=True)):
            self.irt.decimal_places = 2
            with self.assertRaises(ValidationError):
                self.irt.save()

    def test_base_currency_decimals_free_without_documents(self):
        with self.unused():
            self.irt.decimal_places = 2
            self.irt.save()
        self.irt.refresh_from_db()
        self.assertEqual(self.irt.decimal_places, 2)

    def test_base_currency_cannot_be_deactivated(self):
        self.irt.is_active = False
        with self.assertRaises(ValidationError):
            self.irt.full_clean()

    def test_non_base_currency_can_be_deactivated_in_clean(self):
        self.usd.is_active = False
        self.usd.full_clean()


class StoreSettingsBaseCurrencyLockTests(TestCase):
    def setUp(self):
        Currency.objects.create(code="IRT", name="تومان", decimal_places=0)
        Currency.objects.create(code="IQD", name="دینار عراق")
        self.store = StoreSettings.objects.create(store_name="S")

    def test_base_currency_can_change_without_documents(self):
        with patch("core.models._document_sources", sources()):
            self.store.base_currency = "IQD"
            self.store.save()
        self.store.refresh_from_db()
        self.assertEqual(self.store.base_currency, "IQD")

    def test_base_currency_cannot_change_after_documents_on_save(self):
        with patch("core.models._document_sources", sources(has_documents=True)):
            self.store.base_currency = "IQD"
            with self.assertRaises(ValidationError):
                self.store.save()
        self.store.refresh_from_db()
        self.assertEqual(self.store.base_currency, "IRT")

    def test_base_currency_cannot_change_after_documents_in_clean(self):
        with patch("core.models._document_sources", sources(has_documents=True)):
            self.store.base_currency = "IQD"
            with self.assertRaises(ValidationError):
                self.store.full_clean()

    def test_other_fields_can_change_after_documents(self):
        with patch("core.models._document_sources", sources(has_documents=True)):
            self.store.store_name = "New name"
            self.store.save()
        self.store.refresh_from_db()
        self.assertEqual(self.store.store_name, "New name")

    def test_same_base_currency_passes_clean_after_documents(self):
        with patch("core.models._document_sources", sources(has_documents=True)):
            self.store.full_clean()


class PartyOwnerTests(TestCase):
    def test_owner_flag_defaults_to_false(self):
        p = Party.objects.create(name="x")
        self.assertFalse(p.is_owner)

    def test_second_owner_rejected_in_clean(self):
        Party.objects.create(name="A", is_owner=True)
        second = Party(name="B", is_owner=True)
        with self.assertRaises(ValidationError):
            second.full_clean()

    def test_second_owner_rejected_on_save(self):
        Party.objects.create(name="A", is_owner=True)
        with self.assertRaises(ValidationError):
            Party.objects.create(name="B", is_owner=True)
        self.assertEqual(Party.objects.filter(is_owner=True).count(), 1)

    def test_editing_the_owner_is_accepted(self):
        owner = Party.objects.create(name="A", is_owner=True)
        owner.note = "changed"
        owner.full_clean()
        owner.save()

    def test_non_owner_parties_are_unaffected(self):
        Party.objects.create(name="A", is_owner=True)
        Party(name="B").full_clean()

    def test_can_own(self):
        self.assertTrue(Party(name="x", is_owner=True).can_own)
        self.assertTrue(Party(name="x", is_partner=True).can_own)
        self.assertFalse(Party(name="x", is_supplier=True).can_own)
        self.assertFalse(Party(name="x", is_customer=True).can_own)
