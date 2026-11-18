#!/usr/bin/env bash
set -euo pipefail
mkdir -p money tests docs
: > money/__init__.py
: > tests/__init__.py
cat > money/gateway.py <<'SRC'
"""Test stand-in for the MyFatoorah gateway, faithful to how it behaves (see docs/gateway.md)."""
import itertools


class GatewayRefused(Exception):
    def __init__(self, status, field):
        super().__init__(f"MyFatoorah refused refund (HTTP {status}): fields: {field}")
        self.status = status
        self.field = field


class StandInGateway:
    def __init__(self):
        self._ids = itertools.count(1000)
        self.invoices = {}  # invoice_id -> list of transactions
        self.refunds_sent = []

    def authorize(self, invoice_id, amount):
        payment_id = f"PAY-{next(self._ids)}"
        self.invoices.setdefault(invoice_id, []).append(
            {"payment_id": payment_id, "kind": "authorization", "amount": amount, "refunds": []})
        return payment_id

    def capture(self, invoice_id, hold_payment_id):
        """A capture is recorded as a NEW transaction of the hold's invoice, with its own payment id."""
        hold = self._transaction(invoice_id, hold_payment_id)
        capture_id = f"PAY-{next(self._ids)}"
        self.invoices[invoice_id].append(
            {"payment_id": capture_id, "kind": "capture", "amount": hold["amount"], "refunds": []})
        return capture_id

    def invoice_status(self, invoice_id):
        """What the gateway lists for an invoice: every transaction with its kind and refunds."""
        return [dict(t) for t in self.invoices.get(invoice_id, [])]

    def refund(self, payment_id, amount, external_id):
        for transactions in self.invoices.values():
            for t in transactions:
                if t["payment_id"] == payment_id:
                    if t["kind"] != "capture":
                        raise GatewayRefused(400, "paymentId")
                    t["refunds"].append(external_id)
                    self.refunds_sent.append((payment_id, amount, external_id))
                    return {"refund_id": external_id, "status": "accepted"}
        raise GatewayRefused(404, "paymentId")

    def _transaction(self, invoice_id, payment_id):
        return next(t for t in self.invoices[invoice_id] if t["payment_id"] == payment_id)
SRC
cat > money/refunds.py <<'SRC'
"""Sending rider refunds to the gateway."""
from money.gateway import GatewayRefused


def captured_hold_of(gateway, payment):
    """The gateway's read of the captured hold, or None while the capture is not listed yet."""
    for t in gateway.invoice_status(payment["invoice_id"]):
        if t["kind"] == "capture":
            return {"transaction_payment_id": t["payment_id"], "refunds": list(t["refunds"])}
    return None


def send_refund(gateway, payment, refund):
    """Send one refund. Marks it `sent`, `gateway_refused`, or leaves it `pending` for the settle job."""
    if refund["status"] != "pending":
        return refund
    before = captured_hold_of(gateway, payment)
    listed = [] if before is None else before["refunds"]
    if refund["id"] in listed:  # the gateway already has it: never send twice
        refund["status"] = "sent"
        return refund
    try:
        gateway.refund(payment_id=payment["gateway_payment_id"], amount=refund["amount"], external_id=refund["id"])
    except GatewayRefused as error:
        refund["status"] = "gateway_refused"
        refund["error"] = str(error)
        return refund
    refund["status"] = "sent"
    return refund
SRC
cat > docs/gateway.md <<'SRC'
# Gateway notes (MyFatoorah)

- A ride's payment is first authorized (a hold) and captured when the ride ends.
- `payment["gateway_payment_id"]` is the payment id the gateway returned for the hold.
- Refunds are sent by `money/refunds.py`; a refund the gateway refuses is marked `gateway_refused` and staff are called.
- The settle job retries `pending` refunds every few minutes.
SRC
cat > tests/test_refunds.py <<'SRC'
import unittest

from money.gateway import StandInGateway
from money.refunds import send_refund


class SendRefund(unittest.TestCase):
    def test_refund_that_is_already_listed_is_not_sent_again(self):
        gateway = StandInGateway()
        hold = gateway.authorize("INV-1", 5000)
        gateway.capture("INV-1", hold)
        payment = {"invoice_id": "INV-1", "gateway_payment_id": hold}
        gateway.invoices["INV-1"][-1]["refunds"].append("R-1")
        refund = send_refund(gateway, payment, {"id": "R-1", "amount": 1000, "status": "pending"})
        self.assertEqual(refund["status"], "sent")
        self.assertEqual(gateway.refunds_sent, [])


if __name__ == "__main__":
    unittest.main()
SRC
