FRAGILE_FEE = 3
BULK_SERVICE_QUANTITY = 10
TAX_RATES = {"GB": 0.2, "DE": 0.19}


def line_subtotal(item):
    quantity = item.get("qty", 1)
    amount = quantity * item["price"]
    if item.get("type") == "svc":
        return amount * 0.9 if quantity > BULK_SERVICE_QUANTITY else amount
    return amount + FRAGILE_FEE if item.get("fragile") else amount


def items_subtotal(items):
    subtotal = 0
    for item in items:
        subtotal = subtotal + line_subtotal(item)
    return subtotal


def coupon_discount(customer, coupon):
    if coupon != "VIP":
        return 0
    return 25 if customer.get("tier") == "gold" else 15


def loyalty_discounted(customer, subtotal):
    if customer.get("tier") == "gold" and subtotal > 200:
        return subtotal * 0.95
    return subtotal


def tax(customer, subtotal):
    if customer.get("exempt"):
        return 0
    return subtotal * TAX_RATES.get(customer.get("country"), 0)


def inv(c, items, cp=None):
    subtotal = items_subtotal(items) - coupon_discount(c, cp)
    subtotal = max(loyalty_discounted(c, subtotal), 0)
    return round(subtotal + tax(c, subtotal), 2)
