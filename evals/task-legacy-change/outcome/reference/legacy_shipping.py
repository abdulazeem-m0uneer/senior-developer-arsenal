FREE_SHIPPING_OVER = 100


def fee(o):
    t = o.get("total", 0); c = o.get("country", "US"); w = o.get("weight", 0); x = o.get("express")
    if t > FREE_SHIPPING_OVER:
        return 0
    if c == "US":
        f = 5
        if w > 20: f = f + 7
        if x: f = f * 2
    elif c in ("CA", "MX"):
        f = 9
        if w > 20: f = f + 11
        if x: f = f * 2 + 1
    else:
        f = 20
        if w > 20: f = f + 25
        if x: f = f * 3
    return f
