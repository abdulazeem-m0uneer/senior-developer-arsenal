def apply_discount(total, percent):
    """Return the total after a percentage discount between 0 and 100."""
    if not 0 <= percent <= 100:
        raise ValueError(f"percent must be between 0 and 100, got {percent}")
    return total - total * percent / 100


def cart_total(prices, percent=0):
    return apply_discount(sum(prices), percent)
