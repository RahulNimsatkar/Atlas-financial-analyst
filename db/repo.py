"""Repository — all DB operations in one place."""
from datetime import datetime
from typing import List, Optional

from db.models import (
    Alert, Document, Message, ProfileFact, SessionLocal, User, WatchlistItem,
)

SHORT_TERM_LIMIT = 10  # messages injected into each prompt


# ---------- users ----------

def get_or_create_user(tg_id: int, name: str = "") -> User:
    with SessionLocal() as s:
        user = s.query(User).filter_by(tg_id=tg_id).first()
        if not user:
            user = User(tg_id=tg_id, name=name)
            s.add(user)
            s.commit()
        elif name and not user.name:
            user.name = name
            s.commit()
        return user


def update_user(user_id: int, **fields) -> None:
    with SessionLocal() as s:
        s.query(User).filter_by(id=user_id).update(fields)
        s.commit()


def all_users() -> List[User]:
    with SessionLocal() as s:
        return s.query(User).all()


# ---------- conversation memory ----------

def add_message(user_id: int, role: str, content: str) -> None:
    with SessionLocal() as s:
        s.add(Message(user_id=user_id, role=role, content=content))
        s.commit()


def recent_messages(user_id: int, limit: int = SHORT_TERM_LIMIT) -> List[Message]:
    with SessionLocal() as s:
        rows = (
            s.query(Message)
            .filter_by(user_id=user_id)
            .order_by(Message.id.desc())
            .limit(limit)
            .all()
        )
        return list(reversed(rows))


# ---------- long-term facts ----------

def add_fact(user_id: int, fact: str) -> None:
    fact = fact.strip()
    if not fact:
        return
    with SessionLocal() as s:
        exists = s.query(ProfileFact).filter_by(user_id=user_id, fact=fact).first()
        if not exists:
            s.add(ProfileFact(user_id=user_id, fact=fact))
            s.commit()


def get_facts(user_id: int) -> List[str]:
    with SessionLocal() as s:
        return [f.fact for f in s.query(ProfileFact).filter_by(user_id=user_id).all()]


# ---------- watchlist ----------

def add_to_watchlist(user_id: int, ticker: str) -> bool:
    ticker = ticker.upper().strip()
    with SessionLocal() as s:
        if s.query(WatchlistItem).filter_by(user_id=user_id, ticker=ticker).first():
            return False
        s.add(WatchlistItem(user_id=user_id, ticker=ticker))
        s.commit()
        return True


def remove_from_watchlist(user_id: int, ticker: str) -> bool:
    with SessionLocal() as s:
        row = s.query(WatchlistItem).filter_by(
            user_id=user_id, ticker=ticker.upper().strip()
        ).first()
        if not row:
            return False
        s.delete(row)
        s.commit()
        return True


def get_watchlist(user_id: int) -> List[str]:
    with SessionLocal() as s:
        return [w.ticker for w in s.query(WatchlistItem).filter_by(user_id=user_id).all()]


# ---------- alerts ----------

def create_alert(user_id: int, type: str, ticker: str = "",
                 threshold_pct: float = 0.0, remind_at: Optional[datetime] = None,
                 note: str = "") -> Alert:
    with SessionLocal() as s:
        alert = Alert(user_id=user_id, type=type, ticker=ticker.upper(),
                      threshold_pct=threshold_pct, remind_at=remind_at, note=note)
        s.add(alert)
        s.commit()
        return alert


def active_alerts(user_id: Optional[int] = None, type: Optional[str] = None) -> List[Alert]:
    with SessionLocal() as s:
        q = s.query(Alert).filter_by(active=True)
        if user_id is not None:
            q = q.filter_by(user_id=user_id)
        if type is not None:
            q = q.filter_by(type=type)
        return q.all()


def deactivate_alert(alert_id: int) -> None:
    with SessionLocal() as s:
        s.query(Alert).filter_by(id=alert_id).update({"active": False})
        s.commit()


def update_alert(alert_id: int, **fields) -> None:
    with SessionLocal() as s:
        s.query(Alert).filter_by(id=alert_id).update(fields)
        s.commit()


def cancel_alerts_for_ticker(user_id: int, ticker: str) -> int:
    with SessionLocal() as s:
        n = (s.query(Alert)
             .filter_by(user_id=user_id, ticker=ticker.upper(), active=True)
             .update({"active": False}))
        s.commit()
        return n


# ---------- documents ----------

def save_document(user_id: int, kind: str, name: str, content: str) -> None:
    with SessionLocal() as s:
        # only the newest doc stays active for Q&A
        s.query(Document).filter_by(user_id=user_id).update({"active": False})
        s.add(Document(user_id=user_id, kind=kind, name=name,
                       content=content, active=True))
        s.commit()


def active_document(user_id: int) -> Optional[Document]:
    with SessionLocal() as s:
        return (s.query(Document)
                .filter_by(user_id=user_id, active=True)
                .order_by(Document.id.desc())
                .first())
