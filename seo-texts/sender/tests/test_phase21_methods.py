"""Тесты NEW-BACKEND методов analytics/gates/sender/suppression (Фаза 2.1):
rate_series, capacity_report, active_trips, mailbox_readiness, Suppression.stats.
"""

import os
import sys
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.store import (  # noqa: E402
    Store, RecipientIn, CampaignIn, EventIn, MailboxState, SuppressionIn,
)
from sender.analytics import Analytics, CapacitySnapshot, RateSnapshot  # noqa: E402
from sender.suppression import Suppression  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "m.db"))
    s.init_schema()
    yield s
    s.close()


def _mbstate(mid, **kw):
    base = dict(mailbox_id=mid, provider="mailru", day_key="2026-07-19",
                sent_today=0, sent_total=0, ramp_day=0, daily_limit=50,
                last_sent_at=None, paused=False, pause_reason=None)
    base.update(kw)
    return MailboxState(**base)


# ---- analytics.rate_series ----

def test_rate_series_length_and_last_day(store):
    r = store.upsert_recipient(RecipientIn(email="a@m.ru", domain="m.ru"))
    cid = store.create_campaign(CampaignIn(name="C", legal_entity="ООО", legal_inn="1"))
    now = datetime.now(timezone.utc)
    store.append_event(EventIn(dedup_key="s1", event_type="sent", event_ts=now,
                               recipient_id=r, campaign_id=cid))
    store.append_event(EventIn(dedup_key="b1", event_type="bounce", event_ts=now,
                               recipient_id=r, campaign_id=cid))
    series = Analytics(store).rate_series(scope="campaign", target=cid, days=7)
    assert len(series) == 7
    assert all(isinstance(s, RateSnapshot) for s in series)
    assert series[-1].sent == 1 and series[-1].bounce == 1
    assert series[-1].bounce_rate == 100.0
    assert series[0].sent == 0  # неделю назад пусто


def test_rate_series_buckets_isolate_days(store):
    r = store.upsert_recipient(RecipientIn(email="a@m.ru", domain="m.ru"))
    cid = store.create_campaign(CampaignIn(name="C", legal_entity="ООО", legal_inn="1"))
    today = datetime.now(timezone.utc)
    yesterday = today - timedelta(days=1)
    store.append_event(EventIn(dedup_key="t", event_type="sent", event_ts=today,
                               recipient_id=r, campaign_id=cid))
    store.append_event(EventIn(dedup_key="y", event_type="sent", event_ts=yesterday,
                               recipient_id=r, campaign_id=cid))
    series = Analytics(store).rate_series(scope="campaign", target=cid, days=3)
    # ровно по 1 в позавчера-вчера-сегодня? вчера=1, сегодня=1
    assert series[-1].sent == 1  # сегодня
    assert series[-2].sent == 1  # вчера


def test_rate_series_bad_scope(store):
    from sender.analytics import ValidationError
    with pytest.raises(ValidationError):
        Analytics(store).rate_series(scope="planet", target="x", days=3)


# ---- analytics.capacity_report ----

def test_capacity_report(store):
    store.upsert_mailbox_state(_mbstate("mb1", sent_today=10, daily_limit=50))
    store.upsert_mailbox_state(_mbstate("mb2", sent_today=0, daily_limit=30, paused=True))
    cap = Analytics(store).capacity_report("pool_x", mailbox_ids=["mb1", "mb2"])
    assert isinstance(cap, CapacitySnapshot)
    assert cap.mailbox_count == 2
    assert cap.daily_capacity == 80 and cap.sent_today == 10
    assert cap.remaining_today == 70 and cap.utilization_pct == 12.5
    assert cap.paused_mailboxes == 1


def test_capacity_missing_mailbox_skipped(store):
    store.upsert_mailbox_state(_mbstate("mb1", daily_limit=50))
    cap = Analytics(store).capacity_report("p", mailbox_ids=["mb1", "ghost"])
    assert cap.mailbox_count == 1 and cap.daily_capacity == 50


def test_capacity_zero_cap_no_divzero(store):
    store.upsert_mailbox_state(_mbstate("mb1", daily_limit=0, sent_today=0))
    cap = Analytics(store).capacity_report("p", mailbox_ids=["mb1"])
    assert cap.utilization_pct == 0.0


# ---- suppression.stats ----

def test_suppression_stats(store):
    store.suppression_add(SuppressionIn(scope="email", value="a@m.ru", reason="complaint"))
    store.suppression_add(SuppressionIn(scope="domain", value="x.ru", reason="competitor"))
    past = datetime.now(timezone.utc) - timedelta(days=1)
    store.suppression_add(SuppressionIn(scope="inn", value="7701", reason="manual", expires_at=past))
    s = Suppression(store).stats()
    assert s["total"] == 3
    assert s["by_scope"] == {"email": 1, "domain": 1, "inn": 1}
    assert s["active"] == 2 and s["expired"] == 1


# ---- gates.active_trips + sender.mailbox_readiness (нужен config) ----

@pytest.fixture
def wired(tmp_path):
    os.environ.update({f"BOX{i}_PASSWORD": "p" for i in range(1, 6)})
    os.environ["UNSUB_SIGNING_SECRET"] = "s" * 32
    from sender.tests.test_config import BASE_YAML
    from sender.config import Config
    from sender.suppression import Suppression as Sup
    from sender.gates import Gates
    from sender.sender import Sender
    (tmp_path / "c.yaml").write_text(
        BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "t.db")), encoding="utf-8")
    cfg = Config.load(tmp_path / "c.yaml")
    st = Store(str(tmp_path / "t.db")); st.init_schema()
    gates = Gates(cfg, st)
    sender = Sender(cfg, st, Sup(st), gates, dry_run=True)
    return cfg, st, gates, sender


def test_active_trips_empty_on_clean(wired):
    _, _, gates, _ = wired
    assert gates.active_trips() == []


def test_active_trips_reports_global(wired):
    cfg, st, gates, _ = wired
    r = st.upsert_recipient(RecipientIn(email="a@m.ru", domain="m.ru"))
    cid = st.create_campaign(CampaignIn(name="C", legal_entity="ООО", legal_inn="1"))
    now = datetime.now(timezone.utc)
    # global complaint gate: min_volume=50, порог 0.1% → 60 sent + 1 complaint = 1.6%
    for i in range(60):
        st.append_event(EventIn(dedup_key=f"s{i}", event_type="sent", event_ts=now,
                                recipient_id=r, campaign_id=cid))
    st.append_event(EventIn(dedup_key="c1", event_type="complaint", event_ts=now,
                            recipient_id=r, campaign_id=cid))
    trips = gates.active_trips()
    assert any(t.scope == "global" and t.tripped for t in trips)


def test_mailbox_readiness_states(wired):
    cfg, st, _, sender = wired
    win_now = datetime(2026, 7, 14, 9, 0, tzinfo=timezone.utc)  # вт 12:00 МСК — в окне
    # no_state остался ТОЛЬКО для ящика, которого нет и в конфиге. Ящик из
    # конфига без строки состояния (ни одной отправки) — полноправный, с
    # нулевыми счётчиками: иначе «Ёмкость пулов» пропускала добавленные почты
    # (правка по замечанию владельца 28.07).
    assert sender.mailbox_readiness("нет-такого@rusprom.ru").reasons == ("no_state",)
    r0 = sender.mailbox_readiness("box1@rusprom.ru", now=win_now)
    assert "no_state" not in r0.reasons and r0.sent_today == 0
    # готов
    st.upsert_mailbox_state(_mbstate("box1@rusprom.ru", provider="yandex",
                                     daily_limit=50, sent_today=0))
    r = sender.mailbox_readiness("box1@rusprom.ru", now=win_now)
    assert r.ready is True and r.reasons == ()
    # квота: day_key = день win_now, иначе счётчик считается вчерашним и
    # обнуляется (правка 28.07 — «пулы не обновляются по дням»)
    st.upsert_mailbox_state(_mbstate("box2@rusprom.ru", provider="yandex",
                                     day_key="2026-07-14",
                                     daily_limit=3, sent_today=5))
    r2 = sender.mailbox_readiness("box2@rusprom.ru", now=win_now)
    assert r2.ready is False and "quota_exhausted" in r2.reasons
    # вне окна (воскресенье)
    r3 = sender.mailbox_readiness("box1@rusprom.ru",
                                  now=datetime(2026, 7, 19, 9, 0, tzinfo=timezone.utc))
    assert "outside_window" in r3.reasons
