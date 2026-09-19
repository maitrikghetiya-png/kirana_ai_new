"""
FastAPI Server and AWS Lambda Entrypoint for KiranaAI.
Compatible with standard ASGI servers (Uvicorn) and AWS Lambda (via Mangum).
"""

import os
import urllib.parse
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from mangum import Mangum

from agent import kirana_agent
from db import db
from reminder_service import run_autonomous_reminders

app = FastAPI(
    title="KiranaAI API",
    description="AI agent for Indian kirana shop owners to manage customer udhaar.",
    version="1.0.0",
)

# Enable CORS for frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


class PhoneUpdateRequest(BaseModel):
    customer_name: str
    phone: str


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "KiranaAI",
        "bedrock_active": kirana_agent.bedrock_available,
        "dynamodb_aws": db.use_aws,
    }


def _enrich_customers_with_whatsapp(customers):
    enriched = []
    for c in customers:
        name = c.get("customer_name", "")
        bal = c.get("balance", 0)
        phone = c.get("phone", "")
        clean_phone = "".join(ch for ch in phone if ch.isdigit())
        if clean_phone and len(clean_phone) == 10:
            clean_phone = "91" + clean_phone
        text = f"Namaste {name} ji, aapka Kirana store par ₹{bal:.0f} ka udhaar baki hai. Kripya samay milte hi chukta kar dein. Dhanyawad! - Kirana Store"
        enc = urllib.parse.quote(text)
        wa_url = f"https://wa.me/{clean_phone}?text={enc}" if clean_phone else f"https://api.whatsapp.com/send?text={enc}"
        enriched.append({
            **c,
            "whatsapp_url": wa_url,
            "reminder_text": text,
        })
    return enriched


@app.get("/api/dues")
def get_dues_endpoint():
    """Returns the current list of all customers and their outstanding balances with WhatsApp links."""
    customers = db.get_dues()
    enriched = _enrich_customers_with_whatsapp(customers)
    total_due = sum(c.get("balance", 0) for c in customers if c.get("balance", 0) > 0)
    return {
        "customers": enriched,
        "total_outstanding": total_due,
        "total_customers": len(customers),
    }


@app.post("/api/customer/phone")
def update_phone_endpoint(req: PhoneUpdateRequest):
    """Updates customer's phone number for direct WhatsApp messaging."""
    res = db.update_customer_phone(req.customer_name, req.phone)
    return {"status": "success", **res}



@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    """Processes natural language shopkeeper input via Strands Agent and returns response + live ledger state."""
    result = kirana_agent.process_query(req.message)
    # Refresh current ledger state for immediate frontend sync
    current_dues = db.get_dues()
    enriched = _enrich_customers_with_whatsapp(current_dues)
    total_due = sum(c.get("balance", 0) for c in current_dues if c.get("balance", 0) > 0)

    return {
        **result,
        "ledger": {
            "customers": enriched,
            "total_outstanding": total_due,
        }
    }


@app.post("/api/reset")
def reset_endpoint():
    """Resets ledger data for hackathon demo testing."""
    db.reset_all()
    return {"status": "success", "message": "Udhaar khata reset successfully."}


@app.post("/api/reminders/trigger")
def trigger_autonomous_reminder():
    """
    Autonomous reminder flow:
    Checks DynamoDB for outstanding balances and invokes send_reminder without a chat request.
    Invoked directly by EventBridge Scheduler or manual demo trigger.
    """
    result = run_autonomous_reminders({"source": "eventbridge.scheduler"})
    current_dues = db.get_dues()
    enriched = _enrich_customers_with_whatsapp(current_dues)
    total_due = sum(c.get("balance", 0) for c in current_dues if c.get("balance", 0) > 0)
    return {
        **result,
        "ledger": {
            "customers": enriched,
            "total_outstanding": total_due,
        }
    }


# Mount frontend static assets
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    def serve_frontend():
        index_file = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.exists(index_file):
            with open(index_file, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        return HTMLResponse(content="<h1>KiranaAI Frontend Loading...</h1>")


# AWS Lambda entrypoint
_asgi_handler = Mangum(app, lifespan="off")


def lambda_handler(event, context):
    """
    Unified AWS Lambda Handler:
    - If triggered by AWS EventBridge Schedule, runs autonomous reminder check.
    - If triggered by API Gateway / HTTP, delegates to FastAPI ASGI application.
    """
    if isinstance(event, dict) and (
        event.get("source") == "aws.events"
        or "detail-type" in event
        or event.get("action") == "autonomous_reminder"
    ):
        return run_autonomous_reminders(event, context)

    return _asgi_handler(event, context)

