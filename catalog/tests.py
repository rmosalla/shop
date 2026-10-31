from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from .models import Category, Product, Variant


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

    def test_str_returns_sku(self):
        v = Variant.objects.create(product=self.product, sku="DELL-5420-A")
        self.assertEqual(str(v), "DELL-5420-A")

    def test_attributes_are_stored_and_loaded(self):
        v = Variant.objects.create(
            product=self.product,
            sku="DELL-5420-A",
            attributes={"ram": 16, "ssd": 512},
        )
        v.refresh_from_db()
        self.assertEqual(v.attributes, {"ram": 16, "ssd": 512})

    def test_duplicate_sku_rejected(self):
        Variant.objects.create(product=self.product, sku="DELL-5420-A")
        second = Variant(product=self.product, sku="DELL-5420-A")
        with self.assertRaises(ValidationError):
            second.full_clean()

    def test_blank_sku_rejected(self):
        v = Variant(product=self.product, sku="")
        with self.assertRaises(ValidationError):
            v.full_clean()

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


class VariantUniquenessTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Laptop")
        self.product = Product.objects.create(
            category=category, brand="Dell", model_name="Latitude 5420"
        )
        self.other_product = Product.objects.create(
            category=category, brand="HP", model_name="EliteBook 840"
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
