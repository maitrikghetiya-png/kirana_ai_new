"""
DynamoDB storage layer for KiranaAI Udhaar Khata.
Supports both Amazon DynamoDB (AWS) and local fallback store.
"""

import os
import time
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
import json

TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME", "KiranaAI_Udhaar")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
LOCAL_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
LOCAL_DB_FILE = os.path.join(LOCAL_DATA_DIR, "local_dynamodb.json")


class DynamoDBManager:
    def __init__(self):
        self.table_name = TABLE_NAME
        self.use_aws = False
        self.table = None
        self.dynamodb = None
        self._init_client()

    def _init_client(self):
        """Attempts to initialize real AWS DynamoDB if credentials exist, otherwise falls back to local persistence."""
        has_aws_keys = bool(os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"))
        has_aws_profile = bool(os.path.exists(os.path.expanduser("~/.aws/credentials")))
        endpoint_url = os.getenv("DYNAMODB_ENDPOINT_URL")  # e.g., for DynamoDB Local

        if has_aws_keys or has_aws_profile or endpoint_url:
            try:
                import boto3
                kwargs = {"region_name": AWS_REGION}
                if endpoint_url:
                    kwargs["endpoint_url"] = endpoint_url
                self.dynamodb = boto3.resource("dynamodb", **kwargs)
                self._ensure_table_exists()
                self.table = self.dynamodb.Table(self.table_name)
                self.table.load()
                self.use_aws = True
                print(f"[KiranaDB] Connected to Amazon DynamoDB table: {self.table_name}")
                return
            except Exception as e:
                print(f"[KiranaDB] AWS DynamoDB connection not available ({e}). Using local persistent store.")
        else:
            print("[KiranaDB] No AWS credentials detected. Running with local persistent store.")

        self.use_aws = False
        self._init_local_store()

    def _init_local_store(self):
        os.makedirs(LOCAL_DATA_DIR, exist_ok=True)
        if not os.path.exists(LOCAL_DB_FILE):
            self._save_local_store({"customers": {}, "transactions": []})

    def _load_local_store(self) -> Dict[str, Any]:
        try:
            with open(LOCAL_DB_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {"customers": {}, "transactions": []}

    def _save_local_store(self, data: Dict[str, Any]):
        with open(LOCAL_DB_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def _ensure_table_exists(self):
        """Creates DynamoDB table if it doesn't already exist."""
        try:
            existing_tables = [t.name for t in self.dynamodb.tables.all()]
            if self.table_name not in existing_tables:
                print(f"[KiranaDB] Creating DynamoDB table {self.table_name}...")
                table = self.dynamodb.create_table(
                    TableName=self.table_name,
                    KeySchema=[
                        {"AttributeName": "PK", "KeyType": "HASH"},
                        {"AttributeName": "SK", "KeyType": "RANGE"},
                    ],
                    AttributeDefinitions=[
                        {"AttributeName": "PK", "AttributeType": "S"},
                        {"AttributeName": "SK", "AttributeType": "S"},
                    ],
                    BillingMode="PAY_PER_REQUEST",
                )
                table.wait_until_exists()
                print(f"[KiranaDB] Table {self.table_name} created successfully.")
        except Exception as e:
            print(f"[KiranaDB] Note on table check: {e}")

    def add_credit(self, customer_name: str, amount: float, description: str = "") -> Dict[str, Any]:
        """
        Records a credit transaction (customer took items on credit).
        Increases customer balance by amount.
        """
        norm_name = customer_name.strip().title()
        now = datetime.utcnow().isoformat()
        tx_id = f"TX#{int(time.time() * 1000)}"

        if self.use_aws and self.table:
            resp = self.table.update_item(
                Key={"PK": f"CUSTOMER#{norm_name}", "SK": "PROFILE"},
                UpdateExpression="SET customer_name = :name, balance = if_not_exists(balance, :zero) + :val, updated_at = :now",
                ExpressionAttributeValues={
                    ":name": norm_name,
                    ":val": Decimal(str(amount)),
                    ":zero": Decimal("0"),
                    ":now": now,
                },
                ReturnValues="ALL_NEW",
            )
            new_balance = float(resp["Attributes"]["balance"])

            self.table.put_item(
                Item={
                    "PK": f"CUSTOMER#{norm_name}",
                    "SK": tx_id,
                    "type": "CREDIT",
                    "amount": Decimal(str(amount)),
                    "description": description or "Credit purchase",
                    "timestamp": now,
                }
            )
        else:
            data = self._load_local_store()
            cust = data["customers"].get(norm_name, {"customer_name": norm_name, "balance": 0.0, "updated_at": now})
            cust["balance"] = round(cust["balance"] + float(amount), 2)
            cust["updated_at"] = now
            data["customers"][norm_name] = cust
            data["transactions"].append({
                "id": tx_id,
                "customer_name": norm_name,
                "type": "CREDIT",
                "amount": float(amount),
                "description": description or "Credit purchase",
                "timestamp": now,
            })
            self._save_local_store(data)
            new_balance = cust["balance"]

        return {
            "customer_name": norm_name,
            "amount_added": float(amount),
            "new_balance": new_balance,
            "description": description,
            "timestamp": now,
        }

    def record_payment(self, customer_name: str, amount: float) -> Dict[str, Any]:
        """
        Records a payment received from customer.
        Decreases customer balance by amount.
        """
        norm_name = customer_name.strip().title()
        now = datetime.utcnow().isoformat()
        tx_id = f"TX#{int(time.time() * 1000)}"

        if self.use_aws and self.table:
            resp = self.table.update_item(
                Key={"PK": f"CUSTOMER#{norm_name}", "SK": "PROFILE"},
                UpdateExpression="SET customer_name = :name, balance = if_not_exists(balance, :zero) - :val, updated_at = :now",
                ExpressionAttributeValues={
                    ":name": norm_name,
                    ":val": Decimal(str(amount)),
                    ":zero": Decimal("0"),
                    ":now": now,
                },
                ReturnValues="ALL_NEW",
            )
            new_balance = float(resp["Attributes"]["balance"])

            self.table.put_item(
                Item={
                    "PK": f"CUSTOMER#{norm_name}",
                    "SK": tx_id,
                    "type": "PAYMENT",
                    "amount": Decimal(str(amount)),
                    "description": "Payment received",
                    "timestamp": now,
                }
            )
        else:
            data = self._load_local_store()
            cust = data["customers"].get(norm_name, {"customer_name": norm_name, "balance": 0.0, "updated_at": now})
            cust["balance"] = round(cust["balance"] - float(amount), 2)
            cust["updated_at"] = now
            data["customers"][norm_name] = cust
            data["transactions"].append({
                "id": tx_id,
                "customer_name": norm_name,
                "type": "PAYMENT",
                "amount": float(amount),
                "description": "Payment received",
                "timestamp": now,
            })
            self._save_local_store(data)
            new_balance = cust["balance"]

        return {
            "customer_name": norm_name,
            "payment_received": float(amount),
            "remaining_balance": new_balance,
            "timestamp": now,
        }

    def update_customer_phone(self, customer_name: str, phone: str) -> Dict[str, Any]:
        """Sets or updates the mobile phone number for a customer (for WhatsApp reminders)."""
        norm_name = customer_name.strip().title()
        clean_phone = "".join(c for c in phone if c.isdigit())
        now = datetime.utcnow().isoformat()

        if self.use_aws and self.table:
            self.table.update_item(
                Key={"PK": f"CUSTOMER#{norm_name}", "SK": "PROFILE"},
                UpdateExpression="SET customer_name = if_not_exists(customer_name, :name), phone = :p, updated_at = :now",
                ExpressionAttributeValues={
                    ":name": norm_name,
                    ":p": clean_phone,
                    ":now": now
                },
                ReturnValues="ALL_NEW",
            )
        else:
            data = self._load_local_store()
            cust = data["customers"].get(norm_name, {"customer_name": norm_name, "balance": 0.0, "updated_at": now})
            cust["phone"] = clean_phone
            cust["updated_at"] = now
            data["customers"][norm_name] = cust
            self._save_local_store(data)

        return {"customer_name": norm_name, "phone": clean_phone}

    def get_dues(self, customer_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieves dues for a specific customer or all customers.
        """
        if customer_name:
            norm_name = customer_name.strip().title()
            if self.use_aws and self.table:
                resp = self.table.get_item(Key={"PK": f"CUSTOMER#{norm_name}", "SK": "PROFILE"})
                if "Item" in resp:
                    item = resp["Item"]
                    return [{
                        "customer_name": item["customer_name"],
                        "balance": float(item.get("balance", 0)),
                        "phone": item.get("phone", ""),
                        "updated_at": item.get("updated_at", ""),
                    }]
                return []
            else:
                data = self._load_local_store()
                if norm_name in data["customers"]:
                    return [data["customers"][norm_name]]
                return []

        if self.use_aws and self.table:
            resp = self.table.scan(
                FilterExpression="SK = :sk",
                ExpressionAttributeValues={":sk": "PROFILE"},
            )
            items = resp.get("Items", [])
            results = [
                {
                    "customer_name": item["customer_name"],
                    "balance": float(item.get("balance", 0)),
                    "phone": item.get("phone", ""),
                    "updated_at": item.get("updated_at", ""),
                }
                for item in items
            ]
            results.sort(key=lambda x: x["balance"], reverse=True)
            return results
        else:
            data = self._load_local_store()
            results = list(data["customers"].values())
            results.sort(key=lambda x: x["balance"], reverse=True)
            return results

    def reset_all(self):
        """Resets data for a clean testing slate."""
        if self.use_aws and self.table:
            scan = self.table.scan()
            with self.table.batch_writer() as batch:
                for each in scan.get("Items", []):
                    batch.delete_item(Key={"PK": each["PK"], "SK": each["SK"]})
        else:
            self._save_local_store({"customers": {}, "transactions": []})


# Global singleton instance
db = DynamoDBManager()
