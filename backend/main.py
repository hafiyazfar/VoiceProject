from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, List
from enum import Enum
from datetime import datetime
from pathlib import Path
import re
import uuid

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(
    title="VoicePay Backend",
    description="Backend API for a voice-based money transfer prototype.",
    version="1.0.0",
)

# Allow frontend apps to connect during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TransactionStatus(str, Enum):
    pending = "pending"
    completed = "completed"
    rejected = "rejected"


class VoiceCommandRequest(BaseModel):
    user_id: str = Field(default="user_001")
    text: str = Field(..., min_length=2, example="Send RM50 to Ali")


class ConfirmTransactionRequest(BaseModel):
    transaction_id: str
    pin: str = Field(..., min_length=4, max_length=6)


class Contact(BaseModel):
    id: str
    name: str
    aliases: List[str]
    phone: Optional[str] = None


class Transaction(BaseModel):
    id: str
    user_id: str
    amount: float
    recipient: Contact
    purpose: Optional[str] = None
    status: TransactionStatus
    risk_level: str
    risk_reason: Optional[str]
    created_at: str


# Mock database. Replace with PostgreSQL later.
USERS: Dict[str, Dict] = {
    "user_001": {
        "name": "Demo User",
        "pin": "1234",
        "balance": 500.00,
        "daily_limit": 300.00,
    }
}

CONTACTS: Dict[str, Contact] = {
    "ali": Contact(id="c001", name="Ali", aliases=["ali"], phone="+60123456789"),
    "ahmad": Contact(id="c002", name="Ahmad", aliases=["ahmad", "mat"], phone="+60123456788"),
    "mother": Contact(id="c003", name="Mother", aliases=["mother", "mom", "ibu", "mak"], phone="+60123456787"),
    "siti": Contact(id="c004", name="Siti", aliases=["siti"], phone="+60123456786"),
}

TRANSACTIONS: Dict[str, Transaction] = {}


def normalize_text(text: str) -> str:
    return text.lower().strip()


def extract_amount(text: str) -> Optional[float]:
    """Extract amount from commands like 'send rm50 to ali' or 'hantar 20 ringgit kat ali'."""
    patterns = [
        r"(?:rm|myr|ringgit)\s*(\d+(?:\.\d{1,2})?)",
        r"(\d+(?:\.\d{1,2})?)\s*(?:rm|myr|ringgit)",
        r"\b(\d+(?:\.\d{1,2})?)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1))

    return None


def find_recipient(text: str) -> Optional[Contact]:
    for contact in CONTACTS.values():
        for alias in contact.aliases:
            if re.search(rf"\b{re.escape(alias)}\b", text):
                return contact
    return None


def extract_purpose(text: str) -> Optional[str]:
    purpose_patterns = [
        r"for\s+(.+)$",
        r"purpose\s+(.+)$",
        r"untuk\s+(.+)$",
        r"sebab\s+(.+)$",
    ]

    for pattern in purpose_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()

    return None


def fraud_check(user_id: str, amount: float, recipient: Contact) -> Dict[str, Optional[str]]:
    user = USERS.get(user_id)
    if not user:
        return {"risk_level": "high", "risk_reason": "Unknown user"}

    if amount > user["balance"]:
        return {"risk_level": "high", "risk_reason": "Amount exceeds wallet balance"}

    if amount > user["daily_limit"]:
        return {"risk_level": "high", "risk_reason": "Amount exceeds daily transfer limit"}

    if amount >= 200:
        return {"risk_level": "medium", "risk_reason": "Large transaction requires extra confirmation"}

    return {"risk_level": "low", "risk_reason": None}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/api")
def api_root():
    return {
        "message": "VoicePay Backend is running",
        "docs": "/docs",
    }


@app.get("/contacts")
def get_contacts():
    return {"contacts": list(CONTACTS.values())}


@app.get("/balance/{user_id}")
def get_balance(user_id: str):
    user = USERS.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "user_id": user_id,
        "balance": user["balance"],
        "currency": "MYR",
    }


@app.post("/voice-command")
def process_voice_command(request: VoiceCommandRequest):
    user = USERS.get(request.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    text = normalize_text(request.text)

    amount = extract_amount(text)
    if amount is None or amount <= 0:
        raise HTTPException(status_code=400, detail="Could not detect a valid amount")

    recipient = find_recipient(text)
    if recipient is None:
        raise HTTPException(status_code=400, detail="Could not detect recipient")

    purpose = extract_purpose(text)
    risk = fraud_check(request.user_id, amount, recipient)

    transaction_id = str(uuid.uuid4())
    transaction = Transaction(
        id=transaction_id,
        user_id=request.user_id,
        amount=amount,
        recipient=recipient,
        purpose=purpose,
        status=TransactionStatus.pending,
        risk_level=risk["risk_level"],
        risk_reason=risk["risk_reason"],
        created_at=datetime.utcnow().isoformat() + "Z",
    )

    TRANSACTIONS[transaction_id] = transaction

    return {
        "status": "pending_confirmation",
        "message": f"Send RM{amount:.2f} to {recipient.name}?",
        "requires_pin": True,
        "transaction": transaction,
    }


@app.post("/confirm")
def confirm_transaction(request: ConfirmTransactionRequest):
    transaction = TRANSACTIONS.get(request.transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if transaction.status != TransactionStatus.pending:
        raise HTTPException(status_code=400, detail="Transaction is not pending")

    user = USERS.get(transaction.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if request.pin != user["pin"]:
        transaction.status = TransactionStatus.rejected
        TRANSACTIONS[transaction.id] = transaction
        raise HTTPException(status_code=401, detail="Invalid PIN")

    if transaction.amount > user["balance"]:
        transaction.status = TransactionStatus.rejected
        TRANSACTIONS[transaction.id] = transaction
        raise HTTPException(status_code=400, detail="Insufficient balance")

    user["balance"] -= transaction.amount
    transaction.status = TransactionStatus.completed
    TRANSACTIONS[transaction.id] = transaction

    return {
        "status": "success",
        "message": f"RM{transaction.amount:.2f} sent to {transaction.recipient.name}",
        "remaining_balance": user["balance"],
        "transaction": transaction,
    }


@app.get("/transactions")
def get_transactions(user_id: Optional[str] = None):
    transactions = list(TRANSACTIONS.values())

    if user_id:
        transactions = [tx for tx in transactions if tx.user_id == user_id]

    return {"transactions": transactions}


@app.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: str):
    transaction = TRANSACTIONS.get(transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return transaction


# Serve the premium frontend at "/". Mounted last so API routes win.
if FRONTEND_DIR.exists() and (FRONTEND_DIR / "index.html").exists():
    app.mount(
        "/",
        StaticFiles(directory=str(FRONTEND_DIR), html=True),
        name="frontend",
    )
else:
    @app.get("/")
    def _root_fallback():
        return {"message": "VoicePay Backend is running", "docs": "/docs"}
