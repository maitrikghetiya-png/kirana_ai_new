"""
Automated verification tests for KiranaAI Hackathon MVP.
Verifies the exact 4 MUST WORK scenarios:
1. "Ramesh liya 500 doodh" -> record ₹500 credit for Ramesh
2. "Kaun paisa dena hai?" -> show customers and outstanding balances
3. "Ramesh ne 300 de diye" -> record payment and show ₹200 remaining
4. Reminder -> identify customers with pending balances and generate a reminder automatically
"""

import unittest
from backend.db import db
from backend.tools import add_transaction, get_dues, record_payment, send_reminder
from backend.agent import kirana_agent
from fastapi.testclient import TestClient
from backend.handler import app


class TestKiranaAI(unittest.TestCase):

    def setUp(self):
        # Clean slate for each test
        db.reset_all()

    def test_direct_tools_flow(self):
        """Tests the 4 tools directly."""
        # 1. add_transaction
        res1 = add_transaction(customer_name="Ramesh", amount=500.0, description="doodh")
        self.assertIn("500", res1)
        self.assertIn("Ramesh", res1)
        self.assertEqual(db.get_dues("Ramesh")[0]["balance"], 500.0)

        # 2. get_dues
        res2 = get_dues()
        self.assertIn("Ramesh", res2)
        self.assertIn("500", res2)

        # 3. record_payment
        res3 = record_payment(customer_name="Ramesh", amount=300.0)
        self.assertIn("300", res3)
        self.assertIn("200", res3)
        self.assertEqual(db.get_dues("Ramesh")[0]["balance"], 200.0)

        # 4. send_reminder
        res4 = send_reminder()
        self.assertIn("Ramesh", res4)
        self.assertIn("200", res4)
        self.assertIn("Reminder", res4)

    def test_agent_conversation_scenarios(self):
        """Tests the 4 conversational inputs via KiranaAI Agent."""
        # Scenario 1: "Ramesh liya 500 doodh"
        r1 = kirana_agent.process_query("Ramesh liya 500 doodh")
        self.assertEqual(r1.get("tool_called"), "add_transaction")
        self.assertIn("500", r1["response"])
        self.assertIn("Ramesh", r1["response"])
        self.assertEqual(db.get_dues("Ramesh")[0]["balance"], 500.0)

        # Scenario 2: "Kaun paisa dena hai?"
        r2 = kirana_agent.process_query("Kaun paisa dena hai?")
        self.assertEqual(r2.get("tool_called"), "get_dues")
        self.assertIn("Ramesh", r2["response"])
        self.assertIn("500", r2["response"])

        # Scenario 3: "Ramesh ne 300 de diye"
        r3 = kirana_agent.process_query("Ramesh ne 300 de diye")
        self.assertEqual(r3.get("tool_called"), "record_payment")
        self.assertIn("300", r3["response"])
        self.assertIn("200", r3["response"])
        self.assertEqual(db.get_dues("Ramesh")[0]["balance"], 200.0)

        # Scenario 4: "Reminder"
        r4 = kirana_agent.process_query("Reminder")
        self.assertEqual(r4.get("tool_called"), "send_reminder")
        self.assertIn("Ramesh", r4["response"])
        self.assertIn("200", r4["response"])

    def test_api_endpoints(self):
        """Tests FastAPI endpoints."""
        client = TestClient(app)

        # 1. Post credit
        c1 = client.post("/api/chat", json={"message": "Ramesh liya 500 doodh"}).json()
        self.assertEqual(c1["tool_called"], "add_transaction")
        self.assertEqual(c1["ledger"]["total_outstanding"], 500.0)

        # 2. Query dues
        dues = client.get("/api/dues").json()
        self.assertEqual(dues["total_outstanding"], 500.0)
        self.assertEqual(len(dues["customers"]), 1)

        # 3. Post payment
        c2 = client.post("/api/chat", json={"message": "Ramesh ne 300 de diye"}).json()
        self.assertEqual(c2["tool_called"], "record_payment")
        self.assertEqual(c2["ledger"]["total_outstanding"], 200.0)

        # 4. Reminder
        c3 = client.post("/api/chat", json={"message": "Ramesh ko reminder bhejo"}).json()
        self.assertEqual(c3["tool_called"], "send_reminder")
        self.assertIn("200", c3["response"])

    def test_autonomous_reminder_flow(self):
        """
        Tests the autonomous reminder flow:
        Checks DynamoDB directly and invokes send_reminder without a chat request.
        """
        client = TestClient(app)

        # Record ₹500 credit for Ramesh and ₹250 for Suresh
        db.add_credit("Ramesh", 500.0, "doodh")
        db.add_credit("Suresh", 250.0, "atta")

        # Trigger autonomous reminder (EventBridge simulator)
        resp = client.post("/api/reminders/trigger").json()

        self.assertEqual(resp["status"], "reminders_sent")
        self.assertEqual(resp["pending_count"], 2)
        self.assertIn("Ramesh", resp["customers_reminded"])
        self.assertIn("Suresh", resp["customers_reminded"])
        self.assertIn("500", resp["reminder_output"])
        self.assertIn("250", resp["reminder_output"])
        self.assertEqual(resp["ledger"]["total_outstanding"], 750.0)

    def test_lambda_eventbridge_routing(self):
        """Tests that lambda_handler autonomously routes EventBridge scheduled events."""
        from backend.handler import lambda_handler

        db.add_credit("Ramesh", 400.0, "chini")

        # Simulate EventBridge scheduled event payload
        eventbridge_event = {
            "version": "0",
            "id": "event-12345",
            "detail-type": "Scheduled Event",
            "source": "aws.events",
            "time": "2026-09-18T10:00:00Z",
            "region": "us-east-1",
            "resources": ["arn:aws:events:us-east-1:123456789012:rule/DailyReminder"],
            "detail": {}
        }

        result = lambda_handler(eventbridge_event, None)
        self.assertEqual(result["status"], "reminders_sent")
        self.assertIn("Ramesh", result["customers_reminded"])
        self.assertIn("400", result["reminder_output"])

    def test_whatsapp_integration_and_phone_update(self):
        """Tests phone number update and WhatsApp click-to-chat URL formatting."""
        client = TestClient(app)

        db.add_credit("Ramesh", 350.0, "doodh")

        # Update customer phone
        p_resp = client.post("/api/customer/phone", json={"customer_name": "Ramesh", "phone": "9876543210"}).json()
        self.assertEqual(p_resp["status"], "success")
        self.assertEqual(p_resp["phone"], "9876543210")

        # Verify dues endpoint returns enriched whatsapp_url
        dues = client.get("/api/dues").json()
        ramesh = [c for c in dues["customers"] if c["customer_name"] == "Ramesh"][0]
        self.assertEqual(ramesh["phone"], "9876543210")
        self.assertIn("wa.me/919876543210", ramesh["whatsapp_url"])
        self.assertIn("350", ramesh["whatsapp_url"])

        # Verify send_reminder chat includes WhatsApp link
        chat_resp = client.post("/api/chat", json={"message": "Ramesh ko reminder bhejo"}).json()
        self.assertIn("wa.me/919876543210", chat_resp["response"])


if __name__ == "__main__":
    unittest.main()

