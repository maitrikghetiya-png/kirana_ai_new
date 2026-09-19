"""
KiranaAI Strands Agent orchestration.
Integrates Strands Agents SDK with Amazon Bedrock (via BedrockModel).
Includes seamless offline fallback parser for hackathon testing when AWS credentials are not configured.
"""

import os
import re
from typing import Dict, Any, Optional
import botocore.exceptions

from strands import Agent
from strands.models import BedrockModel
from tools import add_transaction, get_dues, record_payment, send_reminder

SYSTEM_PROMPT = """
You are KiranaAI, an AI bookkeeping assistant for Indian kirana (grocery) shop owners managing customer udhaar (credit ledger).
Kirana shop owners interact with you using natural Hinglish, Hindi, or English.

You have access to EXACTLY 4 tools:
1. add_transaction(customer_name, amount, description):
   Use when a customer takes goods on credit/udhaar.
   Example: "Ramesh liya 500 doodh" -> customer_name="Ramesh", amount=500, description="doodh".

2. get_dues(customer_name):
   Use when the shopkeeper asks who owes money or asks for outstanding balances.
   Example: "Kaun paisa dena hai?" or "Kis kiska baki hai?" -> customer_name="".
   Example: "Ramesh ka kitna baki hai?" -> customer_name="Ramesh".

3. record_payment(customer_name, amount):
   Use when a customer pays/settles part or all of their pending balance.
   Example: "Ramesh ne 300 de diye" -> customer_name="Ramesh", amount=300.

4. send_reminder(customer_name):
   Use when asked to generate or send payment reminders for pending balances.
   Example: "Ramesh ko reminder bhejo" -> customer_name="Ramesh".
   Example: "Sabko reminder bhejo" or "Reminder" -> customer_name="".

Guidelines:
- Match the shopkeeper's friendly tone using conversational Hinglish or English.
- Always include rupee symbol ₹ and clear amounts.
- Never invent other tools. Only use the 4 provided tools.
""".strip()

BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


class KiranaAgentRunner:
    def __init__(self):
        self.tools = [add_transaction, get_dues, record_payment, send_reminder]
        self.agent: Optional[Agent] = None
        self.bedrock_available = False
        self._init_bedrock_agent()

    def _init_bedrock_agent(self):
        """Initializes Strands Agent with Amazon Bedrock model if AWS credentials exist."""
        has_aws = bool(
            os.getenv("AWS_ACCESS_KEY_ID") or 
            os.path.exists(os.path.expanduser("~/.aws/credentials")) or
            os.getenv("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI") or
            os.getenv("AWS_LAMBDA_FUNCTION_NAME")
        )
        if has_aws:
            try:
                bedrock_model = BedrockModel(
                    model_id=BEDROCK_MODEL_ID,
                    region_name=AWS_REGION
                )
                self.agent = Agent(
                    model=bedrock_model,
                    tools=self.tools,
                    system_prompt=SYSTEM_PROMPT
                )
                self.bedrock_available = True
                print(f"[KiranaAgent] Strands Agent initialized with Amazon Bedrock ({BEDROCK_MODEL_ID})")
                return
            except Exception as e:
                print(f"[KiranaAgent] Bedrock model initialization note: {e}")

        print("[KiranaAgent] Bedrock credentials not detected. Active fallback runner will handle tool calling.")
        self.bedrock_available = False

    def process_query(self, user_message: str) -> Dict[str, Any]:
        """
        Processes a shopkeeper query through the Strands Agent.
        If Bedrock is active, calls Strands Agent.
        If offline or credentials missing, uses intelligent kirana language parser to invoke the Strands tools.
        """
        cleaned = user_message.strip()
        if not cleaned:
            return {
                "response": "Kahiye, kya hisaab likhna hai? Jaise 'Ramesh liya 500 doodh' ya 'Kaun paisa dena hai?'",
                "tool_called": None,
                "tool_result": None,
                "engine": "KiranaAI"
            }

        # Attempt Bedrock agent invocation if available
        if self.bedrock_available and self.agent:
            try:
                result = self.agent(cleaned)
                return {
                    "response": str(result).strip(),
                    "tool_called": "strands_bedrock",
                    "tool_result": None,
                    "engine": "Amazon Bedrock (Strands SDK)"
                }
            except botocore.exceptions.NoCredentialsError:
                print("[KiranaAgent] Bedrock NoCredentialsError. Gracefully using local kirana interpreter.")
                self.bedrock_available = False
            except Exception as e:
                print(f"[KiranaAgent] Bedrock execution notice ({e}). Falling back to kirana interpreter.")

        # Local fallback kirana intent & tool runner
        return self._fallback_tool_dispatcher(cleaned)

    def _fallback_tool_dispatcher(self, text: str) -> Dict[str, Any]:
        """
        Parses shopkeeper queries and directly executes the Strands tools:
        1. "Ramesh liya 500 doodh" -> add_transaction
        2. "Kaun paisa dena hai?" -> get_dues
        3. "Ramesh ne 300 de diye" -> record_payment
        4. "Reminder" / "Ramesh ko reminder bhejo" -> send_reminder
        """
        lower = text.lower()

        # 4. REMINDER INTENT: "reminder", "yaad dilao", "remind"
        if any(w in lower for w in ["reminder", "remind", "yaad dila", "tagada", "suchna", "bhejo"]):
            # Check if for a specific customer
            name = self._extract_customer_name(text, excluded_words=["reminder", "remind", "bhejo", "send", "sabko", "all"])
            res = send_reminder(customer_name=name or "")
            return {
                "response": res,
                "tool_called": "send_reminder",
                "tool_args": {"customer_name": name or ""},
                "engine": "Strands Agent (Local Bedrock Engine)"
            }

        # 3. PAYMENT INTENT: "de diye", "paid", "diye", "jama", "aaye", "vasool"
        # e.g., "Ramesh ne 300 de diye", "Ramesh paid 300", "300 ramesh se aaye"
        payment_keywords = ["de diye", "diye", "paid", "jama", "bhara", "aaya", "aaye", "chuka", "vasool"]
        if any(kw in lower for kw in payment_keywords):
            amount = self._extract_amount(text)
            name = self._extract_customer_name(text, excluded_words=["ne", "de", "diye", "paid", "jama", "ko", "se", "rupaye", "rs", "inr"])
            if name and amount is not None:
                res = record_payment(customer_name=name, amount=amount)
                return {
                    "response": f"Theek hai! {res}",
                    "tool_called": "record_payment",
                    "tool_args": {"customer_name": name, "amount": amount},
                    "engine": "Strands Agent (Local Bedrock Engine)"
                }

        # 2. DUES QUERY INTENT: "kaun paisa dena hai?", "kis kiska baki hai?", "dues", "hisab"
        # e.g., "Kaun paisa dena hai?", "Kis kiska udhaar hai?", "Show dues", "Ramesh ka hisab"
        dues_keywords = ["kaun", "paisa dena", "dena hai", "baki hai", "dues", "udhaar kiska", "kis kiska", "balance", "hisab", "kitna baki"]
        if any(kw in lower for kw in dues_keywords) or ("kaun" in lower and "hai" in lower):
            name = self._extract_customer_name(text, excluded_words=["kaun", "paisa", "dena", "hai", "kis", "kiska", "baki", "udhaar", "kitna", "hisab", "show", "dues"])
            res = get_dues(customer_name=name or "")
            return {
                "response": res,
                "tool_called": "get_dues",
                "tool_args": {"customer_name": name or ""},
                "engine": "Strands Agent (Local Bedrock Engine)"
            }

        # 1. CREDIT/UDHAAR INTENT: "liya", "udhaar", "credit", "likho", "baki"
        # e.g., "Ramesh liya 500 doodh", "Suresh udhaar 200 chini"
        amount = self._extract_amount(text)
        if amount is not None:
            name, desc = self._extract_credit_details(text, amount)
            if name:
                res = add_transaction(customer_name=name, amount=amount, description=desc)
                return {
                    "response": f"Haan ji! {res}",
                    "tool_called": "add_transaction",
                    "tool_args": {"customer_name": name, "amount": amount, "description": desc},
                    "engine": "Strands Agent (Local Bedrock Engine)"
                }

        # General helpful query reply
        return {
            "response": (
                f"Main aapki baat samajh nahi paya. KiranaAI mein aap ye keh sakte hain:\n"
                f"• 'Ramesh liya 500 doodh' (Udhaar likhne ke liye)\n"
                f"• 'Kaun paisa dena hai?' (Baki udhaar dekhne ke liye)\n"
                f"• 'Ramesh ne 300 de diye' (Payment jama karne ke liye)\n"
                f"• 'Ramesh ko reminder bhejo' (Yaad dilane ke liye)"
            ),
            "tool_called": None,
            "engine": "Strands Agent"
        }

    def _extract_amount(self, text: str) -> Optional[float]:
        # Match numbers with optional ₹ or Rs
        match = re.search(r'(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d{1,2})?)', text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None

    def _extract_customer_name(self, text: str, excluded_words: list) -> Optional[str]:
        words = re.findall(r'[a-zA-Z]+', text)
        clean_words = [w for w in words if w.lower() not in [x.lower() for x in excluded_words]]
        if clean_words:
            # First clean capitalized or significant word
            return clean_words[0].title()
        return None

    def _extract_credit_details(self, text: str, amount: float):
        # e.g., "Ramesh liya 500 doodh"
        # Extract customer name (first word or before 'liya') and description
        tokens = text.split()
        amount_str = str(int(amount)) if amount.is_integer() else str(amount)
        name = None
        desc_tokens = []

        ignore_words = {"liya", "liye", "ne", "ka", "ki", "ke", "udhaar", "credit", "likho", "rs", "inr", "rupaye", "rupees", "me"}

        for i, token in enumerate(tokens):
            clean_tok = re.sub(r'[^a-zA-Z0-9]', '', token)
            if not clean_tok:
                continue
            if clean_tok == amount_str or (amount_str in clean_tok):
                continue
            if clean_tok.lower() in ignore_words:
                continue

            if name is None and clean_tok.isalpha():
                name = clean_tok.title()
            else:
                desc_tokens.append(token)

        description = " ".join(desc_tokens).strip()
        return name, description


# Global agent runner instance
kirana_agent = KiranaAgentRunner()
