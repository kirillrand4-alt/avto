# FILE: sender/tests/test_gates.py
"""Unit tests for sender.gates.

Store is backed by a real temporary SQLite database (per the task): a minimal
implementation of exactly the surface Gates depends on, with the same schema
semantics as the interface contract (events journal, suppression UNIQUE(scope,
value), mailbox_state pause flag). Config is a lightweight fake.
"""

import os
import sqlite3
import sys
import types
from datetime import datetime, timezone

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.gates import Gates, GatesCfg, GateDecision, SuppressionIn  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteStore:
    """Minimal real-sqlite store implementing the slice Gates uses."""

    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path)
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._seq = 0
        self._rc = 0
        self.init_schema()

    def init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS recipients (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                email  TEXT NOT NULL,
                domain TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                dedup_key    TEXT NOT NULL UNIQUE,
                event_type   TEXT NOT NULL,
                recipient_id INTEGER,
                campaign_id  INTEGER,
                mailbox_id   TEXT,
                event_ts     TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS suppression (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                scope       TEXT NOT NULL,
                value       TEXT NOT NULL,
                reason      TEXT NOT NULL,
                source      TEXT,
                campaign_id INTEGER,
                created_at  TEXT NOT NULL,
                expires_at  TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS ux_supp ON suppression(scope, value);
            CREATE TABLE IF NOT EXISTS mailbox_state (
                mailbox_id   TEXT PRIMARY KEY,
                provider     TEXT,
                paused       INTEGER NOT NULL DEFAULT 0,
                pause_reason TEXT,
                updated_at   TEXT
            );
            """
        )
        self._conn.commit()

    # ---- methods used by Gates ----
    def count_events(
        self, *, event_type, campaign_id=None, domain=None, mailbox_id=None, since=None
    ) -> int:
        joins = ""
        where = ["e.event_type = ?"]
        params: list = [event_type]
        if domain is not None:
            joins = " JOIN recipients r ON r.id = e.recipient_id"
            where.append("r.domain = ?")
            params.append(domain)
        if campaign_id is not None:
            where.append("e.campaign_id = ?")
            params.append(campaign_id)
        if mailbox_id is not None:
            where.append("e.mailbox_id = ?")
            params.append(mailbox_id)
        if since is not None:
            where.append("e.event_ts >= ?")
            params.append(since.isoformat() if isinstance(since, datetime) else since)
        q = f"SELECT COUNT(*) FROM events e{joins} WHERE " + " AND ".join(where)
        return int(self._conn.execute(q, params).fetchone()[0])

    def iter_recipients(self, *, valid_status=None, provider=None):
        for row in self._conn.execute("SELECT id, email, domain FROM recipients"):
            yield types.SimpleNamespace(id=row[0], email=row[1], domain=row[2])

    def set_mailbox_paused(self, mailbox_id, paused, reason) -> None:
        self._conn.execute(
            """
            INSERT INTO mailbox_state (mailbox_id, provider, paused, pause_reason, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(mailbox_id) DO UPDATE SET
                paused=excluded.paused,
                pause_reason=excluded.pause_reason,
                updated_at=excluded.updated_at
            """,
            (mailbox_id, "test", 1 if paused else 0, reason, _now()),
        )
        self._conn.commit()

    def suppression_add(self, e: SuppressionIn):
        cur = self._conn.execute(
            """
            INSERT INTO suppression (scope, value, reason, source, campaign_id, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(scope, value) DO NOTHING
            """,
            (
                e.scope,
                e.value,
                e.reason,
                e.source,
                e.campaign_id,
                _now(),
                e.expires_at.isoformat() if e.expires_at else None,
            ),
        )
        self._conn.commit()
        if cur.rowcount == 1:
            return (cur.lastrowid, True)
        row = self._conn.execute(
            "SELECT id FROM suppression WHERE scope=? AND value=?", (e.scope, e.value)
        ).fetchone()
        return (row[0] if row else -1, False)

    # ---- helpers for assertions / seeding ----
    def get_mailbox_state(self, mailbox_id):
        row = self._conn.execute(
            "SELECT mailbox_id, paused, pause_reason FROM mailbox_state WHERE mailbox_id=?",
            (mailbox_id,),
        ).fetchone()
        if row is None:
            return None
        return types.SimpleNamespace(
            mailbox_id=row[0], paused=bool(row[1]), pause_reason=row[2]
        )

    def supp_row(self, scope, value):
        row = self._conn.execute(
            "SELECT reason, source FROM suppression WHERE scope=? AND value=?",
            (scope, value),
        ).fetchone()
        return None if row is None else types.SimpleNamespace(reason=row[0], source=row[1])

    def supp_count(self, scope, value):
        return int(
            self._conn.execute(
                "SELECT COUNT(*) FROM suppression WHERE scope=? AND value=?",
                (scope, value),
            ).fetchone()[0]
        )

    def add_recipient(self, domain, email=None):
        self._rc += 1
        email = email or f"u{self._rc}@{domain}"
        cur = self._conn.execute(
            "INSERT INTO recipients (email, domain) VALUES (?, ?)", (email, domain)
        )
        self._conn.commit()
        return cur.lastrowid

    def add_event(self, event_type, *, recipient_id=None, mailbox_id=None, campaign_id=None):
        self._seq += 1
        self._conn.execute(
            """
            INSERT INTO events (dedup_key, event_type, recipient_id, campaign_id, mailbox_id, event_ts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"t:{self._seq}", event_type, recipient_id, campaign_id, mailbox_id, _now()),
        )
        self._conn.commit()

    def close(self):
        self._conn.close()


class FakeConfig:
    def __init__(self, gates_cfg: GatesCfg, mailbox_ids):
        self._gates = gates_cfg
        self._mbs = [types.SimpleNamespace(mailbox_id=m) for m in mailbox_ids]

    def gates(self):
        return self._gates

    def mailboxes(self):
        return list(self._mbs)


# ---- fixtures / seeding helpers ----

@pytest.fixture
def env(tmp_path):
    store = SqliteStore(str(tmp_path / "gates.db"))
    cfg = FakeConfig(
        GatesCfg(
            domain_bounce_pct=8.0,
            domain_complaint_pct=0.3,
            mailbox_bounce_pct=6.0,
            global_complaint_pct=0.1,
            min_volume=50,
        ),
        mailbox_ids=["box1@rusprom.ru", "box2@rusprom.ru"],
    )
    gates = Gates(cfg, store)
    yield gates, store, cfg
    store.close()


def seed_domain(store, domain, *, sent=0, bounce=0, complaint=0):
    rid = store.add_recipient(domain)
    for _ in range(sent):
        store.add_event("sent", recipient_id=rid)
    for _ in range(bounce):
        store.add_event("bounce", recipient_id=rid)
    for _ in range(complaint):
        store.add_event("complaint", recipient_id=rid)
    return rid


def seed_mailbox(store, mailbox_id, *, sent=0, bounce=0):
    for _ in range(sent):
        store.add_event("sent", mailbox_id=mailbox_id)
    for _ in range(bounce):
        store.add_event("bounce", mailbox_id=mailbox_id)


def _global(decisions):
    return next(d for d in decisions if d.scope == "global")


def _domain(decisions, target, metric):
    return next(
        d
        for d in decisions
        if d.scope == "domain" and d.target == target and d.metric == metric
    )


# ---- happy path ----

def test_no_events_nothing_trips(env):
    gates, store, _ = env
    decisions = gates.evaluate_all()
    assert all(not d.tripped for d in decisions)
    assert all(d.action == "none" for d in decisions)
    # 1 global + 2 mailboxes, no recipients -> no domain decisions
    assert [d.scope for d in decisions] == ["global", "mailbox", "mailbox"]
    assert store.get_mailbox_state("box1@rusprom.ru") is None
    assert store.get_mailbox_state("box2@rusprom.ru") is None


def test_check_decision_shape(env):
    gates, store, _ = env
    seed_domain(store, "shape.ru", sent=100, bounce=1)
    d = gates.check_domain("shape.ru")
    assert isinstance(d, GateDecision)
    assert d.scope == "domain" and d.target == "shape.ru"
    assert d.tripped is False and d.action == "none"
    assert d.metric == "bounce_rate" and d.threshold == 8.0


# ---- domain bounce gate ----

def test_domain_bounce_trips_and_suppresses(env):
    gates, store, _ = env
    seed_domain(store, "acme.ru", sent=100, bounce=12)  # 12% > 8%
    d = gates.check_domain("acme.ru")
    assert d.tripped and d.metric == "bounce_rate" and d.action == "pause"

    gates.evaluate_all()
    row = store.supp_row("domain", "acme.ru")
    assert row is not None and row.reason == "bounce_hard"
    assert row.source == "gate:bounce_rate"


def test_domain_bounce_boundary_is_not_tripped(env):
    gates, store, _ = env
    seed_domain(store, "edge.ru", sent=100, bounce=8)  # exactly 8.0% -> not > 8.0
    assert gates.check_domain("edge.ru").tripped is False

    store2_rid = store.add_recipient("edge2.ru")
    for _ in range(100):
        store.add_event("sent", recipient_id=store2_rid)
    for _ in range(9):
        store.add_event("bounce", recipient_id=store2_rid)  # 9% > 8%
    assert gates.check_domain("edge2.ru").tripped is True


def test_domain_min_volume_guard(env):
    gates, store, _ = env
    seed_domain(store, "tiny.ru", sent=10, bounce=8)  # 80% but < min_volume(50)
    d = gates.check_domain("tiny.ru")
    assert d.tripped is False and d.action == "none"
    gates.evaluate_all()
    assert store.supp_row("domain", "tiny.ru") is None


# ---- domain complaint gate ----

def test_domain_complaint_trips(env):
    gates, store, _ = env
    seed_domain(store, "spam.ru", sent=100, complaint=1)  # 1.0% > 0.3%
    d = gates.check_domain("spam.ru")
    assert d.tripped and d.metric == "complaint_rate"

    gates.evaluate_all()
    row = store.supp_row("domain", "spam.ru")
    assert row is not None and row.reason == "complaint"


# ---- global gate ----

def test_global_complaint_trips_without_pausing_mailboxes(env):
    gates, store, _ = env
    # 1000 sent, 2 complaints -> 0.2% > 0.1% global; domain stays under 0.3%.
    seed_domain(store, "global.ru", sent=1000, complaint=2)
    decisions = gates.evaluate_all()

    g = _global(decisions)
    assert g.tripped and g.metric == "complaint_rate" and g.action == "pause"
    # gates does NOT pause mailboxes on a global trip (orchestrator owns that)
    assert store.get_mailbox_state("box1@rusprom.ru") is None
    assert store.get_mailbox_state("box2@rusprom.ru") is None
    # domain itself is below its own threshold -> not suppressed
    assert store.supp_row("domain", "global.ru") is None


# ---- mailbox gate ----

def test_mailbox_bounce_trips_and_pauses(env):
    gates, store, _ = env
    seed_mailbox(store, "box1@rusprom.ru", sent=100, bounce=10)  # 10% > 6%
    d = gates.check_mailbox("box1@rusprom.ru")
    assert d.tripped and d.action == "pause"

    gates.evaluate_all()
    st = store.get_mailbox_state("box1@rusprom.ru")
    assert st is not None and st.paused and st.pause_reason == "gate_bounce"
    assert store.get_mailbox_state("box2@rusprom.ru") is None


# ---- idempotency ----

def test_evaluate_all_is_idempotent(env):
    gates, store, _ = env
    seed_domain(store, "dup.ru", sent=100, bounce=20)
    seed_mailbox(store, "box1@rusprom.ru", sent=100, bounce=10)

    gates.evaluate_all()
    gates.evaluate_all()

    assert store.supp_count("domain", "dup.ru") == 1
    st = store.get_mailbox_state("box1@rusprom.ru")
    assert st.paused and st.pause_reason == "gate_bounce"


# ---- resume is only explicit ----

def test_evaluate_all_never_resumes(env):
    gates, store, _ = env
    # pre-existing manual pauses / suppression on otherwise-healthy targets
    gates.trip("mailbox", "box1@rusprom.ru", "manual")
    gates.trip("domain", "good.ru", "manual")
    seed_domain(store, "good.ru", sent=100, bounce=0, complaint=0)  # healthy now
    seed_mailbox(store, "box1@rusprom.ru", sent=100, bounce=0)      # healthy now

    decisions = gates.evaluate_all()

    # no decision ever asks to resume
    assert all(d.action in ("none", "pause") for d in decisions)
    # healthy domain decisions are untripped, yet the suppression stays put
    assert _domain(decisions, "good.ru", "bounce_rate").tripped is False
    assert store.supp_row("domain", "good.ru") is not None
    # the manually paused mailbox is not unpaused
    st = store.get_mailbox_state("box1@rusprom.ru")
    assert st.paused is True


# ---- manual kill-switch ----

def test_trip_mailbox(env):
    gates, store, _ = env
    gates.trip("mailbox", "box2@rusprom.ru", "manual")
    st = store.get_mailbox_state("box2@rusprom.ru")
    assert st.paused and st.pause_reason == "manual"


def test_trip_domain(env):
    gates, store, _ = env
    gates.trip("domain", "Comp.RU", "competitor")
    row = store.supp_row("domain", "comp.ru")  # normalised
    assert row is not None and row.reason == "competitor"


def test_trip_global_pauses_all_mailboxes(env):
    gates, store, _ = env
    gates.trip("global", "*", "incident")
    for mb in ("box1@rusprom.ru", "box2@rusprom.ru"):
        st = store.get_mailbox_state(mb)
        assert st.paused and st.pause_reason == "incident"


def test_trip_unknown_scope_raises(env):
    gates, _, _ = env
    with pytest.raises(ValueError):
        gates.trip("nonsense", "x", "reason")
