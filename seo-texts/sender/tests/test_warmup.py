# FILE: sender/tests/test_warmup.py
"""Тесты живого прогрева `sender.warmup`.

Store — реальная временная sqlite (минимальный DAL, соблюдающий схему и
инварианты по warmup_state/mailbox_state/events). Config и Sender — лёгкие
фейки/моки, чтобы не ходить в сеть.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import pytest

from sender.warmup import (
    EventIn,
    MailboxState,
    RenderedMessage,
    SendResult,
    Warmup,
    WarmupState,
)


UTC = timezone.utc


def _dt(day: int, hour: int = 10) -> datetime:
    # 2025-01-09 — четверг (рабочий день).
    return datetime(2025, 1, day, hour, 0, 0, tzinfo=UTC)


# --------------------------------------------------------------------------
# Минимальный реальный sqlite-store (только то, что нужно warmup)
# --------------------------------------------------------------------------
class SqliteStore:
    """Реальный sqlite-DAL для warmup_state/mailbox_state/events."""

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA synchronous=NORMAL")

    def init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS mailbox_state (
                mailbox_id  TEXT PRIMARY KEY,
                provider    TEXT NOT NULL,
                day_key     TEXT NOT NULL,
                sent_today  INTEGER NOT NULL DEFAULT 0,
                sent_total  INTEGER NOT NULL DEFAULT 0,
                ramp_day    INTEGER NOT NULL DEFAULT 0,
                daily_limit INTEGER NOT NULL,
                last_sent_at TEXT,
                paused      INTEGER NOT NULL DEFAULT 0,
                pause_reason TEXT,
                updated_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS warmup_state (
                mailbox_id        TEXT PRIMARY KEY REFERENCES mailbox_state(mailbox_id),
                phase             TEXT NOT NULL DEFAULT 'ramp',
                ramp_day          INTEGER NOT NULL DEFAULT 0,
                warmup_target     INTEGER NOT NULL DEFAULT 0,
                warmup_sent_today INTEGER NOT NULL DEFAULT 0,
                reputation_score  REAL,
                day_key           TEXT NOT NULL,
                last_warmup_at    TEXT,
                updated_at        TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                dedup_key    TEXT NOT NULL,
                event_type   TEXT NOT NULL,
                message_id   INTEGER,
                recipient_id INTEGER,
                campaign_id  INTEGER,
                mailbox_id   TEXT,
                provider     TEXT,
                event_ts     TEXT NOT NULL,
                detail_json  TEXT,
                created_at   TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS ux_events_dedup ON events(dedup_key);
            """
        )
        self._conn.commit()

    # -- mailbox_state (для сетапа FK) --
    def upsert_mailbox_state(self, s: MailboxState) -> None:
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """
            INSERT INTO mailbox_state
                (mailbox_id, provider, day_key, sent_today, sent_total,
                 ramp_day, daily_limit, last_sent_at, paused, pause_reason, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(mailbox_id) DO UPDATE SET
                provider=excluded.provider, day_key=excluded.day_key,
                sent_today=excluded.sent_today, sent_total=excluded.sent_total,
                ramp_day=excluded.ramp_day, daily_limit=excluded.daily_limit,
                last_sent_at=excluded.last_sent_at, paused=excluded.paused,
                pause_reason=excluded.pause_reason, updated_at=excluded.updated_at
            """,
            (s.mailbox_id, s.provider, s.day_key, s.sent_today, s.sent_total,
             s.ramp_day, s.daily_limit,
             s.last_sent_at.isoformat() if s.last_sent_at else None,
             1 if s.paused else 0, s.pause_reason, now),
        )
        self._conn.commit()

    # -- warmup_state --
    def get_warmup_state(self, mailbox_id: str) -> Optional[WarmupState]:
        row = self._conn.execute(
            "SELECT * FROM warmup_state WHERE mailbox_id=?", (mailbox_id,)
        ).fetchone()
        if row is None:
            return None
        lw = row["last_warmup_at"]
        return WarmupState(
            mailbox_id=row["mailbox_id"],
            phase=row["phase"],
            ramp_day=row["ramp_day"],
            warmup_target=row["warmup_target"],
            warmup_sent_today=row["warmup_sent_today"],
            reputation_score=row["reputation_score"],
            day_key=row["day_key"],
            last_warmup_at=datetime.fromisoformat(lw) if lw else None,
        )

    def upsert_warmup_state(self, s: WarmupState) -> None:
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """
            INSERT INTO warmup_state
                (mailbox_id, phase, ramp_day, warmup_target, warmup_sent_today,
                 reputation_score, day_key, last_warmup_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(mailbox_id) DO UPDATE SET
                phase=excluded.phase, ramp_day=excluded.ramp_day,
                warmup_target=excluded.warmup_target,
                warmup_sent_today=excluded.warmup_sent_today,
                reputation_score=excluded.reputation_score,
                day_key=excluded.day_key, last_warmup_at=excluded.last_warmup_at,
                updated_at=excluded.updated_at
            """,
            (s.mailbox_id, s.phase, s.ramp_day, s.warmup_target, s.warmup_sent_today,
             s.reputation_score, s.day_key,
             s.last_warmup_at.isoformat() if s.last_warmup_at else None, now),
        )
        self._conn.commit()

    # -- events --
    def append_event(self, e: EventIn) -> tuple[int, bool]:
        import json
        now = datetime.now(UTC).isoformat()
        cur = self._conn.execute(
            """
            INSERT INTO events
                (dedup_key, event_type, message_id, recipient_id, campaign_id,
                 mailbox_id, provider, event_ts, detail_json, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(dedup_key) DO NOTHING
            """,
            (e.dedup_key, e.event_type, e.message_id, e.recipient_id, e.campaign_id,
             e.mailbox_id, e.provider, e.event_ts.isoformat(),
             json.dumps(e.detail, ensure_ascii=False), now),
        )
        self._conn.commit()
        if cur.rowcount == 0:
            row = self._conn.execute(
                "SELECT id FROM events WHERE dedup_key=?", (e.dedup_key,)
            ).fetchone()
            return int(row["id"]), False
        return int(cur.lastrowid), True

    def count_events(self, *, event_type: str, mailbox_id: Optional[str] = None) -> int:
        if mailbox_id is None:
            row = self._conn.execute(
                "SELECT COUNT(*) c FROM events WHERE event_type=?", (event_type,)
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) c FROM events WHERE event_type=? AND mailbox_id=?",
                (event_type, mailbox_id),
            ).fetchone()
        return int(row["c"])

    def close(self) -> None:
        self._conn.close()


# --------------------------------------------------------------------------
# Фейки config/sender
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class FakeMailboxCfg:
    mailbox_id: str
    provider: str
    is_warmup_node: bool = False


class FakeConfig:
    def __init__(self, mailboxes: list[FakeMailboxCfg], warmup: dict[str, Any],
                 tz: str = "UTC") -> None:
        self._mailboxes = mailboxes
        self._warmup = warmup
        self._tz = tz

    def mailboxes(self) -> list[FakeMailboxCfg]:
        return self._mailboxes

    def get(self, key: str, default: Any = None) -> Any:
        if key == "warmup":
            return self._warmup
        if key == "timezone":
            return self._tz
        return default

    def ramp_curve(self, provider: str) -> list[int]:
        return list(self._warmup.get("ramp_curve", []))


class FakeSender:
    """Мок sender: пишет вызовы, отдаёт заданные результаты."""

    def __init__(self, result: Any = None, can_send: bool = True) -> None:
        self.calls: list[tuple[Any, RenderedMessage, str]] = []
        self._result = result
        self._can_send = can_send

    def can_send_now(self, mailbox_id: str, *, now: datetime) -> bool:
        return self._can_send

    def send(self, message: Any, rendered: RenderedMessage, mailbox_id: str) -> SendResult:
        self.calls.append((message, rendered, mailbox_id))
        if callable(self._result):
            return self._result(message)
        if self._result is not None:
            return self._result
        return SendResult(ok=True, rfc_message_id=f"rfc-{len(self.calls)}",
                          mailbox_id=mailbox_id, sent_at=None)


# --------------------------------------------------------------------------
# Фикстуры
# --------------------------------------------------------------------------
WARMUP_CFG = {
    "enabled_providers": ["google"],
    "ramp_curve": [2, 3, 5, 8, 12, 18, 25, 35, 50],
    "reply_probability": 0.3,
    "reputation_floor": 0.6,
}

BOX5 = "box5@rusprom.ru"
BOX6 = "box6@rusprom.ru"
BOX1 = "box1@rusprom.ru"


@pytest.fixture
def store(tmp_path):
    st = SqliteStore(str(tmp_path / "sender.db"))
    st.init_schema()
    # mailbox_state нужен для FK warmup_state.
    for mb, prov in ((BOX5, "google"), (BOX6, "google"), (BOX1, "yandex")):
        st.upsert_mailbox_state(MailboxState(
            mailbox_id=mb, provider=prov, day_key="2025-01-09",
            sent_today=0, sent_total=0, ramp_day=0, daily_limit=50,
            last_sent_at=None, paused=False, pause_reason=None,
        ))
    yield st
    st.close()


@pytest.fixture
def config_two_google():
    return FakeConfig(
        mailboxes=[
            FakeMailboxCfg(BOX5, "google", is_warmup_node=True),
            FakeMailboxCfg(BOX6, "google", is_warmup_node=True),
            FakeMailboxCfg(BOX1, "yandex", is_warmup_node=False),
        ],
        warmup=WARMUP_CFG,
    )


@pytest.fixture
def config_single_google():
    return FakeConfig(
        mailboxes=[
            FakeMailboxCfg(BOX5, "google", is_warmup_node=True),
            FakeMailboxCfg(BOX1, "yandex", is_warmup_node=False),
        ],
        warmup=WARMUP_CFG,
    )


# --------------------------------------------------------------------------
# daily_target
# --------------------------------------------------------------------------
def test_daily_target_from_ramp_curve_fresh(store, config_two_google):
    wu = Warmup(config_two_google, store, FakeSender())
    assert wu.daily_target(BOX5, now=_dt(9)) == 2  # curve[0]


def test_daily_target_uses_stored_ramp_day(store, config_two_google):
    store.upsert_warmup_state(WarmupState(
        mailbox_id=BOX5, phase="ramp", ramp_day=2, warmup_target=5,
        warmup_sent_today=0, reputation_score=1.0, day_key="2025-01-09",
        last_warmup_at=None,
    ))
    wu = Warmup(config_two_google, store, FakeSender())
    assert wu.daily_target(BOX5, now=_dt(9)) == 5  # curve[2]


def test_daily_target_advances_on_new_day(store, config_two_google):
    store.upsert_warmup_state(WarmupState(
        mailbox_id=BOX5, phase="ramp", ramp_day=2, warmup_target=5,
        warmup_sent_today=5, reputation_score=1.0, day_key="2025-01-08",
        last_warmup_at=None,
    ))
    wu = Warmup(config_two_google, store, FakeSender())
    # день сменился → ramp_day=3 → curve[3]=8
    assert wu.daily_target(BOX5, now=_dt(9)) == 8


def test_daily_target_zero_for_non_warmup_mailbox(store, config_two_google):
    wu = Warmup(config_two_google, store, FakeSender())
    assert wu.daily_target(BOX1, now=_dt(9)) == 0


def test_daily_target_plateau_at_curve_end(store, config_two_google):
    store.upsert_warmup_state(WarmupState(
        mailbox_id=BOX5, phase="steady", ramp_day=99, warmup_target=50,
        warmup_sent_today=0, reputation_score=1.0, day_key="2025-01-09",
        last_warmup_at=None,
    ))
    wu = Warmup(config_two_google, store, FakeSender())
    assert wu.daily_target(BOX5, now=_dt(9)) == 50  # последний элемент


# --------------------------------------------------------------------------
# reputation
# --------------------------------------------------------------------------
def test_reputation_default_when_no_state(store, config_two_google):
    wu = Warmup(config_two_google, store, FakeSender())
    assert wu.reputation(BOX5) == 1.0


def test_reputation_reads_stored_score(store, config_two_google):
    store.upsert_warmup_state(WarmupState(
        mailbox_id=BOX5, phase="ramp", ramp_day=0, warmup_target=2,
        warmup_sent_today=0, reputation_score=0.72, day_key="2025-01-09",
        last_warmup_at=None,
    ))
    wu = Warmup(config_two_google, store, FakeSender())
    assert wu.reputation(BOX5) == pytest.approx(0.72)


# --------------------------------------------------------------------------
# run_cycle: happy-path
# --------------------------------------------------------------------------
def test_run_cycle_happy_path_sends_target(store, config_two_google):
    sender = FakeSender()
    wu = Warmup(config_two_google, store, sender)
    res = wu.run_cycle(BOX5, now=_dt(9))

    assert res.sent == 2  # curve[0]
    assert res.target == 2
    assert len(sender.calls) == 2
    # все письма ушли соседу того же контура
    assert all(call[0].thread_id == f"warmup:{BOX6}" for call in sender.calls)

    st = store.get_warmup_state(BOX5)
    assert st.warmup_sent_today == 2
    assert st.phase == "ramp"
    assert st.reputation_score == pytest.approx(1.0)  # уже на максимуме
    assert store.count_events(event_type="sent", mailbox_id=BOX5) == 2


def test_run_cycle_no_raw_placeholders_in_rendered(store, config_two_google):
    sender = FakeSender()
    wu = Warmup(config_two_google, store, sender)
    wu.run_cycle(BOX5, now=_dt(9))
    for _, rendered, _ in sender.calls:
        assert rendered.unfilled_fields == ()
        assert "{" not in rendered.body and "{" not in rendered.subject


# --------------------------------------------------------------------------
# run_cycle: идемпотентность дневного лимита
# --------------------------------------------------------------------------
def test_run_cycle_daily_cap_idempotent(store, config_two_google):
    sender = FakeSender()
    wu = Warmup(config_two_google, store, sender)

    first = wu.run_cycle(BOX5, now=_dt(9))
    second = wu.run_cycle(BOX5, now=_dt(9, hour=12))

    assert first.sent == 2
    assert second.sent == 0  # дневной таргет уже выбран
    assert len(sender.calls) == 2
    assert store.get_warmup_state(BOX5).warmup_sent_today == 2


# --------------------------------------------------------------------------
# run_cycle: резюм/смена дня
# --------------------------------------------------------------------------
def test_run_cycle_new_day_resets_counter_and_advances_ramp(store, config_two_google):
    store.upsert_warmup_state(WarmupState(
        mailbox_id=BOX5, phase="ramp", ramp_day=1, warmup_target=3,
        warmup_sent_today=3, reputation_score=1.0, day_key="2025-01-08",
        last_warmup_at=_dt(8),
    ))
    sender = FakeSender()
    wu = Warmup(config_two_google, store, sender)

    res = wu.run_cycle(BOX5, now=_dt(9))

    assert res.target == 5   # ramp_day=2 → curve[2]
    assert res.sent == 5     # счётчик сброшен, шлём полный таргет
    st = store.get_warmup_state(BOX5)
    assert st.ramp_day == 2
    assert st.warmup_sent_today == 5
    assert st.day_key == "2025-01-09"


# --------------------------------------------------------------------------
# run_cycle: гейт репутации
# --------------------------------------------------------------------------
def test_run_cycle_reputation_floor_pauses(store, config_two_google):
    store.upsert_warmup_state(WarmupState(
        mailbox_id=BOX5, phase="ramp", ramp_day=0, warmup_target=2,
        warmup_sent_today=0, reputation_score=0.55, day_key="2025-01-09",
        last_warmup_at=None,
    ))
    sender = FakeSender()
    wu = Warmup(config_two_google, store, sender)

    res = wu.run_cycle(BOX5, now=_dt(9))

    assert res.sent == 0
    assert sender.calls == []
    st = store.get_warmup_state(BOX5)
    assert st.phase == "paused"
    assert st.reputation_score == pytest.approx(0.55)


def test_run_cycle_bounce_drops_reputation_and_pauses(store, config_two_google):
    # старт чуть выше пола: один жёсткий провал уронит ниже floor.
    store.upsert_warmup_state(WarmupState(
        mailbox_id=BOX5, phase="ramp", ramp_day=0, warmup_target=2,
        warmup_sent_today=0, reputation_score=0.7, day_key="2025-01-09",
        last_warmup_at=None,
    ))
    fail = SendResult(ok=False, rfc_message_id=None, mailbox_id=BOX5,
                      sent_at=None, error="550 mailbox unavailable", retryable=False)
    sender = FakeSender(result=fail)
    wu = Warmup(config_two_google, store, sender)

    res = wu.run_cycle(BOX5, now=_dt(9))

    assert res.sent == 0
    assert res.reputation_score == pytest.approx(0.5)  # 0.7 - 0.2
    st = store.get_warmup_state(BOX5)
    assert st.phase == "paused"
    assert store.count_events(event_type="bounce", mailbox_id=BOX5) == 1


# --------------------------------------------------------------------------
# run_cycle: окно/пауза отправки
# --------------------------------------------------------------------------
def test_run_cycle_window_closed_sends_nothing(store, config_two_google):
    sender = FakeSender(can_send=False)
    wu = Warmup(config_two_google, store, sender)

    res = wu.run_cycle(BOX5, now=_dt(9))

    assert res.sent == 0
    assert sender.calls == []
    # состояние всё равно зафиксировано (рамп/день), счётчик 0
    st = store.get_warmup_state(BOX5)
    assert st.warmup_sent_today == 0


# --------------------------------------------------------------------------
# run_cycle: нет соседей — некому греть
# --------------------------------------------------------------------------
def test_run_cycle_no_peers_no_send(store, config_single_google):
    sender = FakeSender()
    wu = Warmup(config_single_google, store, sender)

    res = wu.run_cycle(BOX5, now=_dt(9))

    assert res.sent == 0
    assert sender.calls == []


# --------------------------------------------------------------------------
# run_cycle: неприменимый ящик не плодит состояние
# --------------------------------------------------------------------------
def test_run_cycle_non_warmup_mailbox_noop(store, config_two_google):
    sender = FakeSender()
    wu = Warmup(config_two_google, store, sender)

    res = wu.run_cycle(BOX1, now=_dt(9))

    assert res.sent == 0
    assert res.target == 0
    assert res.reputation_score is None
    assert store.get_warmup_state(BOX1) is None  # состояние не создано


# --------------------------------------------------------------------------
# run_cycle: транзиентная ошибка останавливает цикл без bounce-события
# --------------------------------------------------------------------------
def test_run_cycle_transient_error_stops_without_bounce(store, config_two_google):
    from sender.warmup import TransientError

    def _raise(_message):
        raise TransientError("smtp temporary")

    sender = FakeSender(result=_raise)
    wu = Warmup(config_two_google, store, sender)

    res = wu.run_cycle(BOX5, now=_dt(9))

    assert res.sent == 0
    assert store.count_events(event_type="bounce", mailbox_id=BOX5) == 0
    # репутация не наказывается за транзиент
    assert res.reputation_score == pytest.approx(1.0)


# --------------------------------------------------------------------------
# события идемпотентны (dedup_key)
# --------------------------------------------------------------------------
def test_event_dedup_key_is_idempotent(store):
    e = EventIn(dedup_key="warmup:sent:x:y:2025-01-09:0", event_type="sent",
                event_ts=_dt(9), mailbox_id=BOX5, provider="google")
    _id1, created1 = store.append_event(e)
    _id2, created2 = store.append_event(e)
    assert created1 is True
    assert created2 is False
    assert store.count_events(event_type="sent") == 1
