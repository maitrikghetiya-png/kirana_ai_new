# KiranaAI 🏪

**KiranaAI** is an AI bookkeeping and udhaar (credit) management agent designed for Indian kirana (grocery) shop owners. It understands everyday Hinglish shopkeeper language, orchestrates tools via **Strands Agents SDK** and **Amazon Bedrock**, persists data in **Amazon DynamoDB**, supports autonomous **AWS EventBridge** scheduling, and dispatches real payment reminders directly over **WhatsApp**.

---

## 🏗️ Architecture

```
                                  ┌─────────────────────────────────────────────────────────────┐
                                  │                  KiranaAI Web & Mobile UI                   │
                                  │  • Interactive 4-Step Demo Stepper                          │
                                  │  • Hinglish Natural Language Chat Feed                      │
                                  │  • Live DynamoDB Udhaar Khata Ledger                        │
                                  │  • 1-Click WhatsApp Reminder Dispatch                       │
                                  └──────────────────────────────┬──────────────────────────────┘
                                                                 │ HTTP / JSON
                                                                 ▼
┌────────────────────────────────┐         ┌────────────────────────────────────────────────────┐
│   AWS EventBridge Scheduler    │   OR    │        FastAPI + AWS Lambda ASGI Entrypoint        │
│   (rate(1 day) Cron Trigger)   │         │               (via Mangum adapter)                 │
└───────────────┬────────────────┘         └─────────────────────┬──────────────────────────────┘
                │ EventBridge Event                              │
                └─────────────────────────┬──────────────────────┘
                                          │
                     ┌────────────────────┴────────────────────┐
                     ▼                                         ▼
┌─────────────────────────────────────────┐       ┌─────────────────────────────────────────────┐
│          Strands Agents SDK             │       │               Amazon DynamoDB               │
│  • BedrockModel (Claude 3.5 / Nova)     │       │  • Table: KiranaAI_Udhaar                   │
│  • Resilient local fallback engine      │       │  • Customer Profiles, Balances, & Phones    │
│  • EXACTLY 4 Tools:                     │       │  • Timestamped Transaction Ledger           │
│    1. add_transaction                   │       │  • Single-table schema design               │
│    2. get_dues                          │       └─────────────────────────────────────────────┘
│    3. record_payment                    │                                    │
│    4. send_reminder                     │                                    ▼
└────────────────────┬────────────────────┘                   ┌─────────────────────────────────┐
                     │                                        │     WhatsApp Web / Mobile       │
                     └───────────────────────────────────────►│  Direct Click-to-Chat (wa.me)   │
                                                              └─────────────────────────────────┘
```

---

## 🎯 The 4 Required Tools (`backend/tools.py`)

| Tool | Parameters | Description |
|---|---|---|
| **`add_transaction`** | `customer_name: str`, `amount: float`, `description: str = ""` | Records credit purchases in DynamoDB, increases outstanding balance |
| **`get_dues`** | `customer_name: str = ""` | Queries outstanding balances for a specific customer or all debtors |
| **`record_payment`** | `customer_name: str`, `amount: float` | Records cash/UPI payments received, decrements customer balance |
| **`send_reminder`** | `customer_name: str = ""` | Identifies pending balances, formats polite reminders with direct WhatsApp links |

---

## ⚡ The 4 Guided Demo Flows

KiranaAI features an interactive top banner that lets you test the complete shopkeeper bookkeeping lifecycle:

$$\text{1. Add Credit} \longrightarrow \text{2. Ask Dues} \longrightarrow \text{3. Record Payment} \longrightarrow \text{4. Send Reminder}$$

1. **Step 1: Add Credit**
   - Query: `"Ramesh liya 500 doodh"`
   - Tool Invoked: `add_transaction(customer_name="Ramesh", amount=500.0, description="doodh")`
   - Outcome: Records ₹500 credit for Ramesh. Balance = ₹500.
2. **Step 2: Ask Dues**
   - Query: `"Kaun paisa dena hai?"`
   - Tool Invoked: `get_dues()`
   - Outcome: Lists customers with pending balances (Ramesh: ₹500).
3. **Step 3: Record Payment**
   - Query: `"Ramesh ne 300 de diye"`
   - Tool Invoked: `record_payment(customer_name="Ramesh", amount=300.0)`
   - Outcome: Records ₹300 payment. Remaining balance = ₹200.
4. **Step 4: Send Reminder**
   - Query: `"Ramesh ko reminder bhejo"`
   - Tool Invoked: `send_reminder(customer_name="Ramesh")`
   - Outcome: Formats courteous Hinglish reminder with direct WhatsApp button.

---

## ⏰ Autonomous Reminders & AWS EventBridge

KiranaAI includes an autonomous background runner (`backend/reminder_service.py`) that scans DynamoDB and triggers `send_reminder` **without requiring a chat message**:
- **In AWS**: Triggered by **AWS EventBridge Scheduler** (`rate(1 day)`).
- **In Local Demo**: Triggered via the **"⚡ Run Automatic Reminder"** button in the top navigation bar or `POST /api/reminders/trigger`.
- Detects debtor accounts and produces WhatsApp-ready dispatch cards automatically.

---

## 📱 Real WhatsApp Sending Integration

KiranaAI allows kirana owners to send reminders directly to their customers via WhatsApp:
- **Direct 1-Click WhatsApp Button**: Every reminder includes a green `[ 📱 Send via WhatsApp (व्हाट्सएप पर भेजें) ]` button.
- **Customer Phone Number Support**: Add or edit customer phone numbers in the Udhaar Khata ledger (`POST /api/customer/phone`).
- **Standard `wa.me` Protocol**: Formats links as `https://wa.me/91<phone>?text=<encoded_msg>`, opening WhatsApp with the pre-filled reminder ready to send.

---

## 🚀 Quickstart (Local Run)

### 1. One-Click Launch
```bash
git clone <repo-url>
cd kirana-ai
./run.sh
```
Or manually:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.handler:app --reload --port 8000
```

### 2. Open Dashboard
Visit **[http://localhost:8000](http://localhost:8000)** in your browser.

---

## ☁️ AWS Cloud Deployment (AWS SAM)

KiranaAI is serverless-ready out of the box with AWS SAM (`template.yaml`):
```bash
sam build
sam deploy --guided
```

This deploys:
1. **Amazon DynamoDB Table** (`KiranaAI_Udhaar`)
2. **AWS Lambda Function** (FastAPI backend with Mangum ASGI)
3. **AWS EventBridge Rule** (Daily autonomous reminder schedule)
4. **Amazon Bedrock IAM Permissions** (`bedrock:InvokeModel*`)

---

## 🧪 Automated Test Suite

Run the full automated test suite:
```bash
.venv/bin/python -m unittest tests/test_scenarios.py
```
**Output:**
```text
......
----------------------------------------------------------------------
Ran 6 tests in 0.012s

OK
```

---

## 📁 File Structure

```
kirana-ai/
├── backend/
│   ├── __init__.py
│   ├── db.py               # DynamoDB client (boto3) & customer ledger persistence
│   ├── tools.py            # The 4 Strands @tool implementations
│   ├── agent.py            # Strands Agent + Bedrock orchestration
│   ├── reminder_service.py # Autonomous reminder runner (EventBridge ready)
│   └── handler.py          # FastAPI application & unified Lambda entrypoint
├── frontend/
│   ├── index.html          # Responsive modern web/mobile UI with guided stepper
│   ├── style.css           # Modern theme with saffron, emerald, & WhatsApp styling
│   └── app.js              # Real-time ledger sync, chat, & WhatsApp integration
├── tests/
│   └── test_scenarios.py   # 6 comprehensive unit & integration tests
├── template.yaml           # AWS SAM template (Lambda + DynamoDB + EventBridge)
├── run.sh                  # One-click startup script
├── requirements.txt        # Python package dependencies
├── .env.example            # Environment variables template
└── README.md               # Master project documentation
```
