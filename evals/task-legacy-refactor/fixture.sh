#!/usr/bin/env bash
set -euo pipefail
cat > billing_legacy.py <<'PY'
def inv(c, items, cp=None):
    s = 0
    for i in items:
        q = i.get("qty", 1); p = i["price"]
        if i.get("type") == "svc":
            if q > 10: s = s + q * p * 0.9
            else: s = s + q * p
        else:
            s = s + q * p
            if i.get("fragile"): s = s + 3
    if cp == "VIP" and c.get("tier") != "gold": s = s - 15
    elif cp == "VIP": s = s - 25
    if c.get("tier") == "gold" and s > 200: s = s * 0.95
    if s < 0: s = 0
    t = s * 0.2 if c.get("country") == "GB" else (s * 0.19 if c.get("country") == "DE" else 0)
    if c.get("exempt"): t = 0
    return round(s + t, 2)
PY
