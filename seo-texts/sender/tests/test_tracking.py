"""Тесты open-tracking (sender/tracking.py) по спеке OPEN-TRACKING.

Гоняем РЕАЛЬНЫЕ Store/Config: токены подписываются тем же HMAC-секретом,
что unsub, открытие пишется реальным append_event с дедупом. Сеть и провайдер
не задействованы — только локальная SQLite во временной директории.
"""

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from sender.config import Config
from sender.store import (
    Store,
    RecipientIn,
    CampaignIn,
    SequenceStepIn,
    MessageIn,
)
from sender.tests.test_config import BASE_YAML
from sender.tracking import (
    OpenTracker,
    TrackTokenError,
    text_to_html,
    inject_pixel,
)


@pytest.fixture(autouse=True)
def _env():
    """Секреты ящиков и unsub — как в остальных тестах проекта.

    OpenTracker читает секрет из env по имени legal.unsub_secret_env, а Config.load
    валидирует наличие паролей ящиков, поэтому выставляем всё до сборки.
    """
    os.environ.update({f"BOX{i}_PASSWORD": "p" for i in range(1, 6)})
    os.environ["UNSUB_SIGNING_SECRET"] = "s" * 32
    yield


def _build(tmp_path, *, open_enabled=True, suffix=""):
    """Собрать (tracker, store) на реальном конфиге во временной БД.

    open_enabled прокидываем в блок tracking, чтобы гонять enabled_for в обе стороны.
    suffix разводит файлы, когда в одном тесте нужны два независимых конфига.
    """
    db_path = tmp_path / f"t{suffix}.db"
    store = Store(str(db_path))
    store.init_schema()

    yaml_text = BASE_YAML.replace("/tmp/sender.db", str(db_path))
    flag = "true" if open_enabled else "false"
    yaml_text += f"\ntracking:\n  open_enabled: {flag}\n"

    cfg_path = tmp_path / f"config{suffix}.yaml"
    cfg_path.write_text(yaml_text, encoding="utf-8")

    config = Config.load(str(cfg_path))
    return OpenTracker(config, store), store


def _new_campaign(store, *, name="c", config=None):
    """Кампания с обязательными реквизитами; config пробрасываем как есть."""
    kwargs = dict(name=name, legal_entity="ООО «Руспром»", legal_inn="2221239841")
    if config is not None:
        kwargs["config"] = config
    return store.create_campaign(CampaignIn(**kwargs))


def _prepare_message(store, *, sent_at=None, idem="k1"):
    """Получатель + кампания + шаг + письмо.

    Если sent_at задан — помечаем письмо отправленным (появляется sent_at).
    Иначе оставляем в очереди без sent_at (проверка «письмо не отправлено»).
    """
    rid = store.upsert_recipient(RecipientIn(email="a@b.ru", domain="b.ru"))
    cid = _new_campaign(store)
    sid = store.add_step(
        SequenceStepIn(
            campaign_id=cid,
            step_index=0,
            subject_tmpl="s",
            body_tmpl="b",
            delay_hours=0,
        )
    )
    scheduled = sent_at or datetime.now(timezone.utc)
    # enqueue_message возвращает (id, created) — берём id
    mid, _created = store.enqueue_message(
        MessageIn(
            idempotency_key=idem,
            campaign_id=cid,
            recipient_id=rid,
            sequence_step_id=sid,
            scheduled_at=scheduled,
        )
    )
    if sent_at is not None:
        store.mark_sent(mid, "<rfc@id>", sent_at)
    return mid, rid, cid


# --------------------------------------------------------------------------- #
# 1. Токены: roundtrip
# --------------------------------------------------------------------------- #


def test_token_roundtrip(tmp_path):
    tracker, _ = _build(tmp_path)
    token = tracker.make_token(11, 22, 33)
    payload = tracker.verify_token(token)
    assert payload["mid"] == 11
    assert payload["rid"] == 22
    assert payload["cid"] == 33
    # ts проставляется генератором — просто целое.
    assert isinstance(payload["ts"], int)


# --------------------------------------------------------------------------- #
# 2. Подделки: verify -> TrackTokenError; record_open -> False и никаких событий
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "bad",
    [
        "",  # пустая строка
        "garbage",  # нет разделителя
        "not_base64!!.also_bad!!",  # битый base64
        "a.b.c",  # мусор в частях
    ],
)
def test_verify_rejects_bad_tokens(tmp_path, bad):
    tracker, _ = _build(tmp_path)
    with pytest.raises(TrackTokenError):
        tracker.verify_token(bad)


def test_verify_rejects_foreign_secret(tmp_path):
    """Токен, подписанный чужим секретом, отбивается по Signature mismatch."""
    tracker, _ = _build(tmp_path)
    payload = {"cid": 3, "mid": 1, "rid": 2, "ts": 123}
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    sig = hmac.new(b"other-secret-32-bytes-xxxxxxxxxx", payload_json.encode("utf-8"), hashlib.sha256).digest()
    p64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).rstrip(b"=").decode("ascii")
    s64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    with pytest.raises(TrackTokenError):
        tracker.verify_token(f"{p64}.{s64}")


def test_record_open_ignores_forged(tmp_path):
    """На битый/поддельный токен record_open молча вернёт False (наружу GIF+200)."""
    tracker, store = _build(tmp_path)
    _prepare_message(store, sent_at=datetime.now(timezone.utc) - timedelta(minutes=5))

    for bad in ["", "garbage", "aaa.bbb"]:
        assert tracker.record_open(bad) is False

    # Валидный формат, но испорченная подпись -> тоже False.
    mid, rid, cid = 1, 1, 1
    token = tracker.make_token(mid, rid, cid)
    p, s = token.split(".")
    forged = p + "." + s[:-1] + ("A" if s[-1] != "A" else "B")
    assert tracker.record_open(forged) is False

    assert store.count_events(event_type="open") == 0


# --------------------------------------------------------------------------- #
# 3. Валидное открытие: True + ровно одно событие
# --------------------------------------------------------------------------- #


def test_record_open_creates_single_event(tmp_path):
    tracker, store = _build(tmp_path)
    sent_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    mid, rid, cid = _prepare_message(store, sent_at=sent_at)

    token = tracker.make_token(mid, rid, cid)
    assert tracker.record_open(token) is True
    assert store.count_events(event_type="open") == 1


# --------------------------------------------------------------------------- #
# 4. Дедуп: повторное открытие -> False, событие всё ещё одно
# --------------------------------------------------------------------------- #


def test_record_open_dedup(tmp_path):
    tracker, store = _build(tmp_path)
    sent_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    mid, rid, cid = _prepare_message(store, sent_at=sent_at)

    token = tracker.make_token(mid, rid, cid)
    assert tracker.record_open(token) is True
    # dedup_key=open:<mid> -> второе открытие письма не создаёт событие.
    assert tracker.record_open(token) is False
    assert store.count_events(event_type="open") == 1


# --------------------------------------------------------------------------- #
# 5. Префетч-отсев по возрасту письма
# --------------------------------------------------------------------------- #


def test_record_open_prefetch_filter(tmp_path):
    tracker, store = _build(tmp_path)
    sent_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mid, rid, cid = _prepare_message(store, sent_at=sent_at)
    token = tracker.make_token(mid, rid, cid)

    # +1 сек при min_age_sec=3 — это антиспам-префетч провайдера, не человек.
    assert tracker.record_open(token, now=sent_at + timedelta(seconds=1), min_age_sec=3) is False
    assert store.count_events(event_type="open") == 0

    # +10 сек — засчитываем.
    assert tracker.record_open(token, now=sent_at + timedelta(seconds=10), min_age_sec=3) is True
    assert store.count_events(event_type="open") == 1


# --------------------------------------------------------------------------- #
# 6. Письмо без sent_at (не отправлено) -> False
# --------------------------------------------------------------------------- #


def test_record_open_unsent_message(tmp_path):
    tracker, store = _build(tmp_path)
    mid, rid, cid = _prepare_message(store, sent_at=None)  # mark_sent не вызывали
    token = tracker.make_token(mid, rid, cid)
    assert tracker.record_open(token) is False
    assert store.count_events(event_type="open") == 0


# --------------------------------------------------------------------------- #
# 7. enabled_for: глобальный флаг + per-campaign
# --------------------------------------------------------------------------- #


def test_enabled_for_global_off(tmp_path):
    """Глобальный off -> False при любой кампании."""
    tracker, store = _build(tmp_path, open_enabled=False, suffix="off")
    cid = _new_campaign(store)
    assert tracker.enabled_for(store.get_campaign(cid)) is False
    assert tracker.enabled_for(None) is False


def test_enabled_for_global_on(tmp_path):
    """Глобальный on: решает per-campaign флаг open_tracking (по умолчанию True)."""
    tracker, store = _build(tmp_path)

    cid_off = _new_campaign(store, name="off", config={"open_tracking": False})
    cid_empty = _new_campaign(store, name="empty", config={})

    assert tracker.enabled_for(store.get_campaign(cid_off)) is False
    assert tracker.enabled_for(store.get_campaign(cid_empty)) is True
    # Кампания не передана вовсе — разрешаем при включённом глобальном флаге.
    assert tracker.enabled_for(None) is True


# --------------------------------------------------------------------------- #
# 8. text_to_html: экранирование и переносы
# --------------------------------------------------------------------------- #


def test_text_to_html_escapes_and_breaks():
    out = text_to_html("a<b> & c\nx")
    assert "&lt;b&gt;" in out  # < > экранированы
    assert "&amp;" in out  # & экранирован
    assert "<br>" in out  # перенос строки -> <br>
    assert "white-space:pre-wrap" in out  # исходное форматирование сохраняем


# --------------------------------------------------------------------------- #
# 9. inject_pixel: вставка перед </body>, регистр, отсутствие </body>
# --------------------------------------------------------------------------- #


def test_inject_pixel_before_body_lowercase():
    out = inject_pixel("<html><body>hi</body></html>", "https://t.ru/o/tok")
    assert out.count("<img") == 1
    assert out.index("<img") < out.index("</body>")


def test_inject_pixel_before_body_uppercase():
    out = inject_pixel("<HTML><BODY>hi</BODY></HTML>", "https://t.ru/o/tok")
    assert out.count("<img") == 1
    assert out.index("<img") < out.index("</BODY>")


def test_inject_pixel_no_body_appends():
    out = inject_pixel("<div>hi</div>", "https://t.ru/o/tok")
    assert out.count("<img") == 1
    # Без </body> пиксель дописан в самый конец.
    assert out.rstrip().endswith('style="display:none">')


# --------------------------------------------------------------------------- #
# 10. pixel_url: путь /o/ и сам токен
# --------------------------------------------------------------------------- #


def test_pixel_url_contains_path_and_token(tmp_path):
    tracker, _ = _build(tmp_path)
    token = tracker.make_token(1, 2, 3)
    url = tracker.pixel_url(token)
    assert "/o/" in url
    assert url.endswith(token)
