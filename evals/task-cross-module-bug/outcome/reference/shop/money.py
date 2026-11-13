def to_cents(amount):
    """Convert a decimal amount such as 19.99 to integer cents."""
    return round(amount * 100)


def format_cents(cents):
    return f"{cents // 100}.{cents % 100:02d}"
