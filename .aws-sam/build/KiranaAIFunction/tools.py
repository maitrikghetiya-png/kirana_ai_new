"""
Strands Agent Tools for KiranaAI.
Exactly 4 tools as specified:
1. add_transaction
2. get_dues
3. record_payment
4. send_reminder
"""

import urllib.parse
from strands import tool
from db import db


@tool
def add_transaction(customer_name: str, amount: float, description: str = "") -> str:
    """
    Record an udhaar (credit) transaction when a customer takes goods without immediate payment.
    Increases the customer's total outstanding balance.

    Args:
        customer_name: The name of the customer (e.g. Ramesh, Suresh).
        amount: The monetary amount in INR (₹) of the credit purchase.
        description: Description of the items purchased (e.g. doodh, atta, chini).
    """
    res = db.add_credit(customer_name, amount, description)
    item_desc = f" ({description})" if description else ""
    return (
        f"Udhaar recorded successfully! ₹{res['amount_added']:.0f} credit added for {res['customer_name']}{item_desc}. "
        f"Total outstanding balance is now ₹{res['new_balance']:.0f}."
    )


@tool
def get_dues(customer_name: str = "") -> str:
    """
    Check outstanding balances (udhaar) for a specific customer or all customers.
    Answers questions like 'Kaun paisa dena hai?' or 'Kis kiska udhaar baki hai?'.

    Args:
        customer_name: Optional customer name. If omitted or empty, retrieves all customers with pending dues.
    """
    norm_name = customer_name.strip() if customer_name else None
    if norm_name and norm_name.lower() in ["all", "sab", "sabka", "everyone", "none"]:
        norm_name = None

    dues = db.get_dues(norm_name)

    if not dues:
        if norm_name:
            return f"No records found for customer '{norm_name}'."
        return "Sabka hisaab barabar hai! No customers currently have pending dues."

    if norm_name:
        cust = dues[0]
        bal = cust.get("balance", 0)
        if bal > 0:
            return f"{cust['customer_name']} has an outstanding balance of ₹{bal:.0f}."
        elif bal < 0:
            return f"{cust['customer_name']} has an advance balance of ₹{abs(bal):.0f}."
        else:
            return f"{cust['customer_name']} has cleared all dues (₹0 balance)."

    # All customers summary
    pending = [c for c in dues if c.get("balance", 0) > 0]
    cleared = [c for c in dues if c.get("balance", 0) <= 0]

    if not pending:
        return "All customers have cleared their dues! Current ledger balance is ₹0."

    lines = ["Pending Udhaar (Dues List):"]
    total_due = 0
    for idx, c in enumerate(pending, 1):
        bal = c.get("balance", 0)
        total_due += bal
        lines.append(f"{idx}. {c['customer_name']}: ₹{bal:.0f}")

    lines.append(f"Total outstanding across all customers: ₹{total_due:.0f}")
    return "\n".join(lines)


@tool
def record_payment(customer_name: str, amount: float) -> str:
    """
    Record a payment received from a customer towards their outstanding balance.
    Decreases the customer's pending udhaar and calculates remaining balance.

    Args:
        customer_name: The name of the customer who paid (e.g. Ramesh).
        amount: The amount in INR (₹) paid by the customer.
    """
    res = db.record_payment(customer_name, amount)
    rem = res["remaining_balance"]
    if rem > 0:
        status_msg = f"Remaining balance is ₹{rem:.0f}."
    elif rem == 0:
        status_msg = "Hisab barabar! Full udhaar cleared (₹0 balance)."
    else:
        status_msg = f"Account cleared with advance payment of ₹{abs(rem):.0f}."

    return (
        f"Payment of ₹{res['payment_received']:.0f} received from {res['customer_name']}. "
        f"{status_msg}"
    )


@tool
def send_reminder(customer_name: str = "") -> str:
    """
    Identify customers with pending balances and generate a courteous reminder message.
    Used to send payment notifications or polite reminders for unpaid udhaar.

    Args:
        customer_name: Optional customer name. If omitted or empty, generates reminders for all customers with dues.
    """
    norm_name = customer_name.strip() if customer_name else None
    if norm_name and norm_name.lower() in ["all", "sab", "sabka", "everyone", "none"]:
        norm_name = None

    dues = db.get_dues(norm_name)
    pending = [c for c in dues if c.get("balance", 0) > 0]

    if not pending:
        if norm_name:
            return f"No reminder needed: {norm_name} has no pending balance."
        return "No reminders needed: All customer accounts are settled."

    messages = []
    for c in pending:
        name = c["customer_name"]
        bal = c.get("balance", 0)
        phone = c.get("phone", "")
        clean_phone = "".join(ch for ch in phone if ch.isdigit())
        if clean_phone and len(clean_phone) == 10:
            clean_phone = "91" + clean_phone

        reminder_text = (
            f"Namaste {name} ji, aapka Kirana store par ₹{bal:.0f} ka udhaar baki hai. "
            f"Kripya samay milte hi chukta kar dein. Dhanyawad! - Kirana Store"
        )
        encoded_text = urllib.parse.quote(reminder_text)
        if clean_phone:
            wa_link = f"https://wa.me/{clean_phone}?text={encoded_text}"
        else:
            wa_link = f"https://api.whatsapp.com/send?text={encoded_text}"

        msg = (
            f"🔔 Reminder for {name}:\n"
            f"\"{reminder_text}\"\n"
            f"📱 WhatsApp: {wa_link}"
        )
        messages.append(msg)

    return "\n\n".join(messages)
