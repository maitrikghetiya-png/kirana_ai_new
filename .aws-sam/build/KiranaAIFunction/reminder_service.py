"""
Autonomous reminder service for KiranaAI.
Scans Amazon DynamoDB for outstanding customer balances and invokes send_reminder
without requiring a manual chat request.
Compatible with AWS EventBridge Scheduler and direct demo triggers.
"""

import urllib.parse
from datetime import datetime
from typing import Dict, Any
from db import db
from tools import send_reminder


def run_autonomous_reminders(event: Any = None, context: Any = None) -> Dict[str, Any]:
    """
    Autonomous execution flow:
    1. Scans DynamoDB for all customers with outstanding udhaar (balance > 0).
    2. Automatically invokes the send_reminder tool.
    3. Returns execution metadata and generated reminder messages with direct WhatsApp links.

    Triggered by:
    - AWS EventBridge Scheduler (e.g., cron daily schedule)
    - Manual demonstration trigger via /api/reminders/trigger
    """
    all_dues = db.get_dues()
    pending_customers = [c for c in all_dues if c.get("balance", 0) > 0]

    source = "manual_trigger"
    if isinstance(event, dict):
        source = event.get("source", event.get("detail-type", "aws.events"))

    timestamp = datetime.utcnow().isoformat()

    customer_reminders = []
    for c in pending_customers:
        name = c["customer_name"]
        bal = c.get("balance", 0)
        phone = c.get("phone", "")
        clean_phone = "".join(ch for ch in phone if ch.isdigit())
        if clean_phone and len(clean_phone) == 10:
            clean_phone = "91" + clean_phone
        text = f"Namaste {name} ji, aapka Kirana store par ₹{bal:.0f} ka udhaar baki hai. Kripya samay milte hi chukta kar dein. Dhanyawad! - Kirana Store"
        enc = urllib.parse.quote(text)
        wa_url = f"https://wa.me/{clean_phone}?text={enc}" if clean_phone else f"https://api.whatsapp.com/send?text={enc}"
        customer_reminders.append({
            "customer_name": name,
            "balance": bal,
            "phone": phone,
            "whatsapp_url": wa_url,
            "message": text
        })

    if pending_customers:
        reminder_content = send_reminder()
        status = "reminders_sent"
    else:
        reminder_content = "Sabka hisaab barabar hai. No customers with pending dues found in DynamoDB."
        status = "no_dues_pending"

    return {
        "status": status,
        "triggered_at": timestamp,
        "trigger_source": source,
        "pending_count": len(pending_customers),
        "customers_reminded": [c["customer_name"] for c in pending_customers],
        "total_due": sum(c.get("balance", 0) for c in pending_customers),
        "reminder_output": reminder_content,
        "reminders": customer_reminders,
    }
