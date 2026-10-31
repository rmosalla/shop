from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import TestCase

from .models import Category, Product


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
            p.full_clean()from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import TestCase

from .models import Category, Product


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