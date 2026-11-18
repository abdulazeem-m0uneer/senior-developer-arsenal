import unittest

from money.gateway import StandInGateway
from money.refunds import send_refund


class RefundNamesTheCapture(unittest.TestCase):
    def test_refund_after_capture_is_accepted(self):
        gateway = StandInGateway()
        hold = gateway.authorize("INV-1", 5000)
        gateway.capture("INV-1", hold)
        payment = {"invoice_id": "INV-1", "gateway_payment_id": hold}
        refund = send_refund(gateway, payment, {"id": "R-1", "amount": 1000, "status": "pending"})
        self.assertEqual(refund["status"], "sent")


if __name__ == "__main__":
    unittest.main()
