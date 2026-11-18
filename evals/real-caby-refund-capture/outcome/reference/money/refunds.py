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
    if before is None:  # no captured transaction listed yet: leave it pending; the settle job sends it later
        return refund
    if refund["id"] in before["refunds"]:  # the gateway already has it: never send twice
        refund["status"] = "sent"
        return refund
    try:
        gateway.refund(payment_id=before["transaction_payment_id"], amount=refund["amount"], external_id=refund["id"])
    except GatewayRefused as error:
        refund["status"] = "gateway_refused"
        refund["error"] = str(error)
        return refund
    refund["status"] = "sent"
    return refund
