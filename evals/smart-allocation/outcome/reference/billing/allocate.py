def allocate(total_cents, weights):
    """Split an amount in cents across accounts in proportion to their weights (largest remainder)."""
    weight_sum = sum(weights)
    floors = [total_cents * w // weight_sum for w in weights]
    remainders = [total_cents * w % weight_sum for w in weights]
    order = sorted(range(len(weights)), key=lambda i: (-remainders[i], i))
    for i in order[: total_cents - sum(floors)]:
        floors[i] += 1
    return floors
