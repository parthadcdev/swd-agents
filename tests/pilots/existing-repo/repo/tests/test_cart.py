import unittest

from shop.cart import subtotal


class SubtotalTest(unittest.TestCase):
    def test_sums_price_times_quantity(self):
        self.assertEqual(subtotal([(100, 2), (5, 3)]), 215)

    def test_empty_cart_is_zero(self):
        self.assertEqual(subtotal([]), 0)


if __name__ == "__main__":
    unittest.main()
