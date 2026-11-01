from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from .models import AttributeDefinition, Category, Product, Variant


class CategoryTests(TestCase):
    def test_str_returns_name(self):
        c = Category.objects.create(name="Laptop")
        self.assertEqual(str(c), "Laptop")

    def test_defaults(self):
        c = Category.objects.create(name="Laptop")
        self.assertIsNone(c.parent)
        self.assertTrue(c.is_active)

    def test_children_are_reachable_from_parent(self):
        parent = Category.objects.create(name="Accessories")
        child = Category.objects.create(name="Mouse", parent=parent)
        self.assertEqual(list(parent.children.all()), [child])

    def test_cannot_delete_category_with_children(self):
        parent = Category.objects.create(name="Accessories")
        Category.objects.create(name="Mouse", parent=parent)
        with self.assertRaises(ProtectedError):
            parent.delete()

    def test_duplicate_name_rejected(self):
        Category.objects.create(name="Laptop")
        second = Category(name="Laptop")
        with self.assertRaises(ValidationError):
            second.full_clean()

    def test_category_cannot_be_its_own_parent(self):
        c = Category.objects.create(name="Laptop")
        c.parent = c
        with self.assertRaises(ValidationError):
            c.full_clean()

    def test_new_root_category_passes_full_clean(self):
        Category(name="Laptop").full_clean()

    def test_child_category_passes_full_clean(self):
        parent = Category.objects.create(name="Accessories")
        Category(name="Mouse", parent=parent).full_clean()

    def test_two_level_cycle_rejected(self):
        a = Category.objects.create(name="A")
        b = Category.objects.create(name="B", parent=a)
        a.parent = b
        with self.assertRaises(ValidationError):
            a.full_clean()

    def test_lineage_ids_contains_self_and_ancestors(self):
        root = Category.objects.create(name="Root")
        child = Category.objects.create(name="Child", parent=root)
        grandchild = Category.objects.create(name="Grandchild", parent=child)
        self.assertEqual(grandchild.lineage_ids(), {root.pk, child.pk, grandchild.pk})


class ProductTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Laptop")

    def test_defaults(self):
        p = Product.objects.create(category=self.category, model_name="Latitude 5420")
        self.assertEqual(p.tracking_type, Product.Tracking.SERIALIZED)
        self.assertEqual(p.warranty_months, 0)
        self.assertTrue(p.is_active)

    def test_str_with_brand(self):
        p = Product.objects.create(
            category=self.category, brand="Dell", model_name="Latitude 5420"
        )
        self.assertEqual(str(p), "Dell Latitude 5420")

    def test_str_without_brand_has_no_extra_space(self):
        p = Product.objects.create(category=self.category, model_name="Mouse pad")
        self.assertEqual(str(p), "Mouse pad")

    def test_cannot_delete_category_with_products(self):
        Product.objects.create(category=self.category, model_name="Latitude 5420")
        with self.assertRaises(ProtectedError):
            self.category.delete()

    def test_invalid_tracking_type_rejected(self):
        p = Product(category=self.category, model_name="x", tracking_type="bogus")
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_negative_warranty_rejected(self):
        p = Product(category=self.category, model_name="x", warranty_months=-1)
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_product_without_category_rejected(self):
        p = Product(model_name="x")
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_products_reachable_from_category(self):
        p = Product.objects.create(category=self.category, model_name="x")
        self.assertEqual(list(self.category.products.all()), [p])

    def test_model_name_allows_200_chars(self):
        p = Product(category=self.category, model_name="x" * 200)
        p.full_clean()


class VariantTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Laptop")
        self.product = Product.objects.create(
            category=category, brand="Dell", model_name="Latitude 5420"
        )

    def test_defaults(self):
        v = Variant.objects.create(product=self.product, sku="DELL-5420-A")
        self.assertEqual(v.attributes, {})
        self.assertEqual(v.default_price_base, 0)
        self.assertTrue(v.is_active)

    def test_attributes_are_stored_and_loaded(self):
        v = Variant.objects.create(
            product=self.product,
            sku="DELL-5420-A",
            attributes={"ram": 16, "ssd": 512},
        )
        v.refresh_from_db()
        self.assertEqual(v.attributes, {"ram": 16, "ssd": 512})

    def test_str_returns_sku(self):
        v = Variant.objects.create(product=self.product)
        self.assertEqual(str(v), "DELL-LATITUDE-5420")

    def test_negative_price_rejected(self):
        v = Variant(product=self.product, sku="x", default_price_base=-1)
        with self.assertRaises(ValidationError):
            v.full_clean()

    def test_variant_without_product_rejected(self):
        v = Variant(sku="x")
        with self.assertRaises(ValidationError):
            v.full_clean()

    def test_variants_reachable_from_product(self):
        v = Variant.objects.create(product=self.product, sku="DELL-5420-A")
        self.assertEqual(list(self.product.variants.all()), [v])

    def test_cannot_delete_product_with_variants(self):
        Variant.objects.create(product=self.product, sku="DELL-5420-A")
        with self.assertRaises(ProtectedError):
            self.product.delete()


class VariantSkuTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Laptop")
        self.product = Product.objects.create(
            category=self.category, brand="Dell", model_name="Latitude 5420"
        )

    def test_sku_built_from_product_and_attributes(self):
        v = Variant.objects.create(
            product=self.product, attributes={"ram": 16, "ssd": 512}
        )
        self.assertEqual(v.sku, "DELL-LATITUDE-5420-16-512")

    def test_sku_without_attributes(self):
        v = Variant.objects.create(product=self.product)
        self.assertEqual(v.sku, "DELL-LATITUDE-5420")

    def test_attribute_order_does_not_change_sku(self):
        v = Variant.objects.create(
            product=self.product, attributes={"ssd": 512, "ram": 16}
        )
        self.assertEqual(v.sku, "DELL-LATITUDE-5420-16-512")

    def test_decimal_value_keeps_its_point_as_underscore(self):
        v = Variant.objects.create(product=self.product, attributes={"screen": 15.6})
        self.assertEqual(v.sku, "DELL-LATITUDE-5420-15_6")

    def test_text_value_is_slugified(self):
        v = Variant.objects.create(product=self.product, attributes={"cpu": "Core i7"})
        self.assertEqual(v.sku, "DELL-LATITUDE-5420-CORE-I7")

    def test_duplicate_generated_sku_gets_numeric_suffix(self):
        other = Product.objects.create(
            category=self.category, brand="Dell", model_name="Latitude 5420"
        )
        first = Variant.objects.create(product=self.product)
        second = Variant.objects.create(product=other)
        third_product = Product.objects.create(
            category=self.category, brand="Dell", model_name="Latitude 5420"
        )
        third = Variant.objects.create(product=third_product)
        self.assertEqual(first.sku, "DELL-LATITUDE-5420")
        self.assertEqual(second.sku, "DELL-LATITUDE-5420-2")
        self.assertEqual(third.sku, "DELL-LATITUDE-5420-3")

    def test_non_latin_name_falls_back_to_product_id(self):
        product = Product.objects.create(category=self.category, model_name="لپ‌تاپ")
        v = Variant.objects.create(product=product)
        self.assertEqual(v.sku, f"P{product.pk}")

    def test_long_names_are_truncated(self):
        product = Product.objects.create(
            category=self.category, brand="B" * 90, model_name="M" * 150
        )
        first = Variant.objects.create(product=product)
        other = Product.objects.create(
            category=self.category, brand="B" * 90, model_name="M" * 150
        )
        second = Variant.objects.create(product=other)
        self.assertLessEqual(len(first.sku), 80)
        self.assertLessEqual(len(second.sku), 80)
        self.assertNotEqual(first.sku, second.sku)

    def test_blank_sku_is_allowed_in_full_clean(self):
        v = Variant(product=self.product, attributes={})
        v.full_clean()

    def test_explicit_sku_is_ignored(self):
        v = Variant.objects.create(product=self.product, sku="CUSTOM-1")
        self.assertEqual(v.sku, "DELL-LATITUDE-5420")

    def test_sku_follows_attribute_changes(self):
        v = Variant.objects.create(product=self.product, attributes={"ram": 16})
        self.assertEqual(v.sku, "DELL-LATITUDE-5420-16")
        v.attributes = {"ram": 32}
        v.save()
        self.assertEqual(v.sku, "DELL-LATITUDE-5420-32")

    def test_sku_stays_stable_when_saved_again(self):
        other = Product.objects.create(
            category=self.category, brand="Dell", model_name="Latitude 5420"
        )
        Variant.objects.create(product=self.product)
        second = Variant.objects.create(product=other)
        self.assertEqual(second.sku, "DELL-LATITUDE-5420-2")
        second.save()
        self.assertEqual(second.sku, "DELL-LATITUDE-5420-2")

    def test_other_text_is_added_at_the_end(self):
        v = Variant.objects.create(
            product=self.product,
            attributes={"other": "refurbished", "ram": 16},
        )
        self.assertEqual(v.sku, "DELL-LATITUDE-5420-16-REFURBISHED")

    def test_sku_field_is_not_editable(self):
        self.assertFalse(Variant._meta.get_field("sku").editable)


class VariantUniquenessTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Laptop")
        self.product = Product.objects.create(
            category=category, brand="Dell", model_name="Latitude 5420"
        )
        self.other_product = Product.objects.create(
            category=category, brand="HP", model_name="EliteBook 840"
        )
        AttributeDefinition.objects.create(
            key="ram", label="رم", value_type=AttributeDefinition.ValueType.NUMBER
        )
        AttributeDefinition.objects.create(
            key="ssd", label="SSD", value_type=AttributeDefinition.ValueType.NUMBER
        )

    def test_same_attributes_same_product_rejected(self):
        Variant.objects.create(
            product=self.product, sku="A", attributes={"ram": 16, "ssd": 512}
        )
        second = Variant(
            product=self.product, sku="B", attributes={"ram": 16, "ssd": 512}
        )
        with self.assertRaises(ValidationError):
            second.full_clean()

    def test_attribute_order_does_not_matter(self):
        Variant.objects.create(
            product=self.product, sku="A", attributes={"ram": 16, "ssd": 512}
        )
        second = Variant(
            product=self.product, sku="B", attributes={"ssd": 512, "ram": 16}
        )
        with self.assertRaises(ValidationError):
            second.full_clean()

    def test_two_variants_without_attributes_rejected(self):
        Variant.objects.create(product=self.product, sku="A")
        second = Variant(product=self.product, sku="B")
        with self.assertRaises(ValidationError):
            second.full_clean()

    def test_different_attribute_value_accepted(self):
        Variant.objects.create(
            product=self.product, sku="A", attributes={"ram": 16, "ssd": 512}
        )
        second = Variant(
            product=self.product, sku="B", attributes={"ram": 32, "ssd": 512}
        )
        second.full_clean()

    def test_same_attributes_on_other_product_accepted(self):
        Variant.objects.create(
            product=self.product, sku="A", attributes={"ram": 16, "ssd": 512}
        )
        second = Variant(
            product=self.other_product, sku="B", attributes={"ram": 16, "ssd": 512}
        )
        second.full_clean()

    def test_editing_same_variant_accepted(self):
        v = Variant.objects.create(
            product=self.product, sku="A", attributes={"ram": 16, "ssd": 512}
        )
        v.full_clean()

    def test_database_rejects_duplicate_even_without_clean(self):
        Variant.objects.create(product=self.product, sku="A", attributes={"ram": 16})
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Variant.objects.create(
                    product=self.product, sku="B", attributes={"ram": 16}
                )

    def test_attributes_must_be_a_dict(self):
        v = Variant(product=self.product, sku="A", attributes=[1, 2])
        with self.assertRaises(ValidationError):
            v.full_clean()


class AttributeDefinitionTests(TestCase):
    def test_defaults(self):
        a = AttributeDefinition.objects.create(key="note", label="توضیح")
        self.assertEqual(a.value_type, AttributeDefinition.ValueType.TEXT)
        self.assertEqual(a.choices, [])
        self.assertEqual(a.unit, "")
        self.assertTrue(a.is_active)

    def test_str_returns_label(self):
        a = AttributeDefinition.objects.create(key="ram", label="رم")
        self.assertEqual(str(a), "رم")

    def test_duplicate_key_rejected(self):
        AttributeDefinition.objects.create(key="ram", label="رم")
        second = AttributeDefinition(key="ram", label="حافظه")
        with self.assertRaises(ValidationError):
            second.full_clean()

    def test_invalid_keys_rejected(self):
        for key in ["RAM", "ram size", "رم", "1ram", "ram-size", ""]:
            with self.subTest(key=key):
                a = AttributeDefinition(key=key, label="x")
                with self.assertRaises(ValidationError):
                    a.full_clean()

    def test_valid_keys_accepted(self):
        for key in ["ram", "ssd_size", "m2"]:
            with self.subTest(key=key):
                AttributeDefinition(key=key, label="x").full_clean()

    def test_choice_type_requires_choices(self):
        a = AttributeDefinition(
            key="cpu",
            label="پردازنده",
            value_type=AttributeDefinition.ValueType.CHOICE,
        )
        with self.assertRaises(ValidationError):
            a.full_clean()

    def test_choices_must_be_list_of_strings(self):
        for bad in [[1, 2], "i5", {"a": "b"}]:
            with self.subTest(choices=bad):
                a = AttributeDefinition(
                    key="cpu",
                    label="پردازنده",
                    value_type=AttributeDefinition.ValueType.CHOICE,
                    choices=bad,
                )
                with self.assertRaises(ValidationError):
                    a.full_clean()

    def test_choice_type_with_choices_accepted(self):
        a = AttributeDefinition(
            key="cpu",
            label="پردازنده",
            value_type=AttributeDefinition.ValueType.CHOICE,
            choices=["i5", "i7"],
        )
        a.full_clean()

    def test_non_choice_type_with_choices_rejected(self):
        a = AttributeDefinition(
            key="ram",
            label="رم",
            value_type=AttributeDefinition.ValueType.NUMBER,
            choices=["8", "16"],
        )
        with self.assertRaises(ValidationError):
            a.full_clean()


class VariantAttributeValidationTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Laptop")
        self.product = Product.objects.create(
            category=category, brand="Dell", model_name="Latitude 5420"
        )
        ValueType = AttributeDefinition.ValueType
        AttributeDefinition.objects.create(
            key="ram", label="رم", value_type=ValueType.NUMBER, unit="GB"
        )
        AttributeDefinition.objects.create(
            key="cpu",
            label="پردازنده",
            value_type=ValueType.CHOICE,
            choices=["i5", "i7"],
        )
        AttributeDefinition.objects.create(
            key="note", label="توضیح", value_type=ValueType.TEXT
        )
        AttributeDefinition.objects.create(
            key="hdd", label="هارد", value_type=ValueType.NUMBER, is_active=False
        )

    def make(self, attributes):
        return Variant(product=self.product, sku="X", attributes=attributes)

    def test_unknown_key_rejected(self):
        with self.assertRaises(ValidationError):
            self.make({"RAM": 16}).full_clean()

    def test_inactive_attribute_rejected(self):
        with self.assertRaises(ValidationError):
            self.make({"hdd": 500}).full_clean()

    def test_number_rejects_string(self):
        with self.assertRaises(ValidationError):
            self.make({"ram": "16"}).full_clean()

    def test_number_rejects_boolean(self):
        with self.assertRaises(ValidationError):
            self.make({"ram": True}).full_clean()

    def test_choice_rejects_unlisted_value(self):
        with self.assertRaises(ValidationError):
            self.make({"cpu": "i9"}).full_clean()

    def test_choice_accepts_listed_value(self):
        self.make({"cpu": "i7"}).full_clean()

    def test_text_rejects_empty_string(self):
        with self.assertRaises(ValidationError):
            self.make({"note": ""}).full_clean()

    def test_text_accepts_string(self):
        self.make({"note": "refurbished"}).full_clean()

    def test_multiple_valid_attributes_accepted(self):
        self.make({"ram": 16, "cpu": "i5", "note": "x"}).full_clean()

    def test_empty_attributes_accepted(self):
        self.make({}).full_clean()

    def test_price_with_two_decimals_accepted(self):
        v = Variant(
            product=self.product, sku="x", default_price_base=Decimal("1000.50")
        )
        v.full_clean()

    def test_price_with_three_decimals_rejected(self):
        v = Variant(
            product=self.product, sku="x", default_price_base=Decimal("1000.001")
        )
        with self.assertRaises(ValidationError):
            v.full_clean()


class AttributeCategoryTests(TestCase):
    def setUp(self):
        self.laptops = Category.objects.create(name="Laptop")
        self.gaming = Category.objects.create(name="Gaming", parent=self.laptops)
        self.mice = Category.objects.create(name="Mouse")
        self.laptop = Product.objects.create(category=self.laptops, model_name="X1")
        self.gaming_laptop = Product.objects.create(
            category=self.gaming, model_name="G15"
        )
        self.mouse = Product.objects.create(category=self.mice, model_name="FStyler")
        ValueType = AttributeDefinition.ValueType
        ram = AttributeDefinition.objects.create(
            key="ram", label="رم", value_type=ValueType.NUMBER
        )
        ram.categories.add(self.laptops)
        AttributeDefinition.objects.create(
            key="color", label="رنگ", value_type=ValueType.TEXT
        )

    def test_restricted_attribute_accepted_in_its_own_category(self):
        Variant(product=self.laptop, attributes={"ram": 16}).full_clean()

    def test_restricted_attribute_accepted_in_child_category(self):
        Variant(product=self.gaming_laptop, attributes={"ram": 16}).full_clean()

    def test_restricted_attribute_rejected_in_other_category(self):
        with self.assertRaises(ValidationError):
            Variant(product=self.mouse, attributes={"ram": 16}).full_clean()

    def test_unrestricted_attribute_accepted_everywhere(self):
        for product in [self.laptop, self.gaming_laptop, self.mouse]:
            with self.subTest(product=product):
                Variant(product=product, attributes={"color": "black"}).full_clean()
