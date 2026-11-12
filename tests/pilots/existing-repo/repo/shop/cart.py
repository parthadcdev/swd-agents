"""Shopping cart arithmetic."""


def subtotal(items):
    """Sum of price x quantity for a list of (price, quantity) pairs."""
    return sum(price * quantity for price, quantity in items)


def apply_discount(amount, percent):
    """Return amount reduced by a percentage discount."""
    return amount - percent
