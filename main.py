from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bestoption.db")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-key")
JWT_ALGORITHM = "HS256"

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, default="")
    password_hash = Column(String, default="")
    balance = Column(Float, default=10000.0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Trade(Base):
    __tablename__ = "trades"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("profiles.id"), nullable=False, index=True)
    symbol = Column(String, nullable=False)
    side = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    status = Column(String, default="open")
    realized_pnl = Column(Float, default=0.0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    closed_at = Column(DateTime, nullable=True)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("profiles.id"), nullable=False, index=True)
    type = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    note = Column(String, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("profiles.id"), nullable=False, index=True)
    symbol = Column(String, nullable=False)
    market = Column(String, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


Base.metadata.create_all(bind=engine)


class AuthRequest(BaseModel):
    email: str
    password: str
    full_name: str = ""


class TradeCreate(BaseModel):
    symbol: str
    side: str
    quantity: int = Field(..., gt=0)
    price: float = Field(..., gt=0)
    notes: Optional[str] = None
#curl -s http://127.0.0.1:8000/api/health

class TransactionCreate(BaseModel):
    type: str
    amount: float = Field(..., gt=0)
    note: Optional[str] = None


class WatchlistCreate(BaseModel):
    symbol: str
    market: Optional[str] = None


app = FastAPI(title="BestOption API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def create_token(profile_id: str, email: str) -> str:
    payload = {
        "sub": profile_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def serialize_profile(profile: Profile) -> Dict[str, Any]:
    return {
        "id": profile.id,
        "email": profile.email,
        "full_name": profile.full_name,
        "balance": float(profile.balance or 0.0),
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
    }


def serialize_trade(trade: Trade) -> Dict[str, Any]:
    return {
        "id": trade.id,
        "user_id": trade.user_id,
        "symbol": trade.symbol,
        "side": trade.side,
        "quantity": trade.quantity,
        "price": float(trade.price),
        "status": trade.status,
        "realized_pnl": float(trade.realized_pnl or 0.0),
        "created_at": trade.created_at.isoformat() if trade.created_at else None,
        "closed_at": trade.closed_at.isoformat() if trade.closed_at else None,
    }


def serialize_transaction(txn: Transaction) -> Dict[str, Any]:
    return {
        "id": txn.id,
        "user_id": txn.user_id,
        "type": txn.type,
        "amount": float(txn.amount),
        "note": txn.note,
        "created_at": txn.created_at.isoformat() if txn.created_at else None,
    }


def serialize_watchlist(item: WatchlistItem) -> Dict[str, Any]:
    return {
        "id": item.id,
        "user_id": item.user_id,
        "symbol": item.symbol,
        "market": item.market,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> Profile:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    profile = db.query(Profile).filter(Profile.id == payload.get("sub")).first()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return profile


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/signup")
def signup(payload: AuthRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
    email = payload.email.strip().lower()
    existing = db.query(Profile).filter(Profile.email == email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    profile = Profile(
        email=email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        balance=10000.0,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    token = create_token(profile.id, profile.email)
    return {"token": token, "user": serialize_profile(profile)}


@app.post("/api/auth/login")
def login(payload: AuthRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
    email = payload.email.strip().lower()
    profile = db.query(Profile).filter(Profile.email == email).first()
    if not profile or profile.password_hash != hash_password(payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_token(profile.id, profile.email)
    return {"token": token, "user": serialize_profile(profile)}


@app.get("/api/profile")
def get_profile(current_user: Profile = Depends(get_current_user)) -> Dict[str, Any]:
    return serialize_profile(current_user)


@app.get("/api/trades")
def list_trades(current_user: Profile = Depends(get_current_user), db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    trades = db.query(Trade).filter(Trade.user_id == current_user.id).order_by(Trade.created_at.desc()).all()
    return [serialize_trade(trade) for trade in trades]


@app.post("/api/trades")
def create_trade(payload: TradeCreate, current_user: Profile = Depends(get_current_user), db: Session = Depends(get_db)) -> Dict[str, Any]:
    trade = Trade(
        user_id=current_user.id,
        symbol=payload.symbol.upper(),
        side=payload.side.lower(),
        quantity=payload.quantity,
        price=payload.price,
        status="open",
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return serialize_trade(trade)


@app.post("/api/trades/{trade_id}/close")
def close_trade(trade_id: str, current_user: Profile = Depends(get_current_user), db: Session = Depends(get_db)) -> Dict[str, Any]:
    trade = db.query(Trade).filter(Trade.id == trade_id, Trade.user_id == current_user.id).first()
    if trade is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
    if trade.status == "closed":
        return serialize_trade(trade)

    mark_price = trade.price + 1.25 if trade.side == "buy" else trade.price - 1.25
    pnl = (mark_price - trade.price) * trade.quantity if trade.side == "buy" else (trade.price - mark_price) * trade.quantity
    trade.status = "closed"
    trade.realized_pnl = round(float(pnl), 2)
    trade.closed_at = datetime.now(timezone.utc)
    current_user.balance += trade.realized_pnl
    db.commit()
    db.refresh(trade)
    return serialize_trade(trade)


@app.delete("/api/trades/{trade_id}")
def delete_trade(trade_id: str, current_user: Profile = Depends(get_current_user), db: Session = Depends(get_db)) -> Dict[str, str]:
    trade = db.query(Trade).filter(Trade.id == trade_id, Trade.user_id == current_user.id).first()
    if trade is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
    db.delete(trade)
    db.commit()
    return {"status": "deleted"}


@app.get("/api/watchlist")
def list_watchlist(current_user: Profile = Depends(get_current_user), db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    items = db.query(WatchlistItem).filter(WatchlistItem.user_id == current_user.id).order_by(WatchlistItem.created_at.desc()).all()
    return [serialize_watchlist(item) for item in items]


@app.post("/api/watchlist")
def add_watchlist(payload: WatchlistCreate, current_user: Profile = Depends(get_current_user), db: Session = Depends(get_db)) -> Dict[str, Any]:
    item = WatchlistItem(user_id=current_user.id, symbol=payload.symbol.upper(), market=payload.market or "")
    db.add(item)
    db.commit()
    db.refresh(item)
    return serialize_watchlist(item)


@app.delete("/api/watchlist/{symbol}")
def delete_watchlist(symbol: str, current_user: Profile = Depends(get_current_user), db: Session = Depends(get_db)) -> Dict[str, str]:
    item = db.query(WatchlistItem).filter(WatchlistItem.user_id == current_user.id, WatchlistItem.symbol == symbol.upper()).first()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist item not found")
    db.delete(item)
    db.commit()
    return {"status": "deleted"}


@app.get("/api/transactions")
def list_transactions(current_user: Profile = Depends(get_current_user), db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    transactions = db.query(Transaction).filter(Transaction.user_id == current_user.id).order_by(Transaction.created_at.desc()).all()
    return [serialize_transaction(txn) for txn in transactions]


@app.post("/api/transactions")
def create_transaction(payload: TransactionCreate, current_user: Profile = Depends(get_current_user), db: Session = Depends(get_db)) -> Dict[str, Any]:
    if payload.type not in {"deposit", "withdraw"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Transaction type must be deposit or withdraw")

    if payload.type == "withdraw" and current_user.balance < payload.amount:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient balance")

    txn = Transaction(user_id=current_user.id, type=payload.type, amount=payload.amount, note=payload.note or "")
    db.add(txn)
    if payload.type == "deposit":
        current_user.balance += payload.amount
    else:
        current_user.balance -= payload.amount
    db.commit()
    db.refresh(txn)
    return serialize_transaction(txn)


@app.get("/api/markets")
def list_markets() -> Dict[str, Any]:
    data = {
        "prices": {
            "AAPL": 214.8,
            "MSFT": 449.6,
            "NVDA": 127.4,
            "EURUSD": 1.09,
            "GBPUSD": 1.27,
            "BTCUSD": 61840.0,
            "ETHUSD": 3480.0,
            "XAUUSD": 2314.5,
        }
    }
    return data


@app.get("/")
def index() -> Dict[str, str]:
    return {"message": "BestOption API"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
