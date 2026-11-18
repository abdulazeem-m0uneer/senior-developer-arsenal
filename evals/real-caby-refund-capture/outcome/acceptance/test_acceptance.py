"""Hidden acceptance tests: the agent never sees this file.
Rebuilt from caby-backend #696 (refund the captured transaction's PaymentId, not the hold's)."""
import unittest

from money.gateway import StandInGateway
from money.refunds import send_refund


def captured_payment(gateway, invoice="INV-1", amount=5000):
    hold = gateway.authorize(invoice, amount)
    capture = gateway.capture(invoice, hold)
    return {"invoice_id": invoice, "gateway_payment_id": hold}, capture


class RefundsReachTheCapture(unittest.TestCase):
    def test_card_refund_is_sent(self):
        gateway = StandInGateway()
        payment, capture = captured_payment(gateway)
        refund = send_refund(gateway, payment, {"id": "R-1", "amount": 1000, "status": "pending"})
        self.assertEqual(refund["status"], "sent")
        self.assertEqual(gateway.refunds_sent, [(capture, 1000, "R-1")])

    def test_sent_once(self):
        gateway = StandInGateway()
        payment, _ = captured_payment(gateway)
        refund = {"id": "R-2", "amount": 700, "status": "pending"}
        send_refund(gateway, payment, refund)
        send_refund(gateway, payment, {"id": "R-2", "amount": 700, "status": "pending"})
        self.assertEqual(len(gateway.refunds_sent), 1)

    def test_not_sent_before_the_capture_is_listed(self):
        gateway = StandInGateway()
        hold = gateway.authorize("INV-9", 3000)
        payment = {"invoice_id": "INV-9", "gateway_payment_id": hold}
        refund = send_refund(gateway, payment, {"id": "R-3", "amount": 500, "status": "pending"})
        self.assertEqual(refund["status"], "pending")
        self.assertEqual(gateway.refunds_sent, [])

    def test_payment_record_keeps_the_hold_id(self):
        gateway = StandInGateway()
        payment, _ = captured_payment(gateway)
        hold = payment["gateway_payment_id"]
        send_refund(gateway, payment, {"id": "R-4", "amount": 100, "status": "pending"})
        self.assertEqual(payment["gateway_payment_id"], hold)


if __name__ == "__main__":
    unittest.main()
