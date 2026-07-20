"""Интеграционные тесты обвязки open-tracking.

Проверяем сквозную работу пикселя открытий на трёх уровнях:
  * unsub_server — HTTP-роут /o/<token> (всегда 200 + GIF, кэш выключен);
  * sender — сборка MIME с <img src=pixel_url> (multipart/alternative);
  * analytics/gates — учёт open-событий в отчётах без влияния на гейты.

Наружу сети нет: HTTP-сервер поднимается локально на 127.0.0.1 и свободном
порту (port=0), запросы идут через stdlib urllib. Провайдер не задействован.
"""

import os
import threading
import time
import urllib.request
from types import SimpleNamespace

import pytest

# Сообщение считается "живым" для учёта открытия только если отправлено
# заметно раньше запроса (защита от префетча почтовыми клиентами: они дёргают
# пиксель сразу). Ждём чуть больше порога в 3 секунды.
SENT_AGE_WAIT = 3.2


def _set_env() -> None:
    """Выставить обязательные секреты ДО Config.load.

    Config при загрузке подтягивает пароли ящиков и секрет подписи из
    окружения, поэтому переменные должны существовать раньше загрузки.
    """
    for i in range(1, 6):
        os.environ[f"BOX{i}_PASSWORD"] = "test-password"
    # Секрет подписи токенов: требуется длина 32+ символа.
    os.environ["UNSUB_SIGNING_SECRET"] = "u" * 40


@pytest.fixture
def config(tmp_path):
    """Конфиг на базе BASE_YAML: db в tmp, open-tracking включён."""
    _set_env()
    from sender.config import Config
    from sender.tests.test_config import BASE_YAML

    db_path = tmp_path / "sender.db"
    yaml_text = BASE_YAML.replace("/tmp/sender.db", str(db_path))
    # Включаем открытия — иначе _open_pixel_url вернёт None и пиксель не встанет.
    yaml_text += "\ntracking:\n  open_enabled: true\n"

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml_text, encoding="utf-8")
    return Config.load(str(cfg_path))


@pytest.fixture
def store(config):
    """Хранилище с инициализированной схемой."""
    from sender.store import Store

    st = Store(config.get("service.db_path"))
    st.init_schema()
    return st


@pytest.fixture
def suppression(store):
    from sender.suppression import Suppression

    return Suppression(store)


@pytest.fixture
def server(config, store, suppression):
    """Локальный HTTP-сервер отписки/пикселя на свободном порту."""
    from sender.unsub_server import make_server

    srv = make_server(config, store, suppression, host="127.0.0.1", port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    host, port = srv.server_address
    try:
        yield srv, f"http://{host}:{port}"
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def _get(base_url: str, path: str):
    """GET по локальному серверу. Возвращает (status, body_bytes, headers)."""
    with urllib.request.urlopen(base_url + path, timeout=5) as resp:
        return resp.status, resp.read(), resp.headers


def _open_token(tracker, message_id):
    """Получить пиксель-токен для сообщения.

    Имя метода-генератора токена может отличаться между ревизиями трекера,
    поэтому пробуем несколько привычных вариантов, симметричных record_open.
    """
    return tracker.make_token(message_id, 1, 1)


def _seed_sent_message(store):
    """Создать получателя, кампанию, шаг и ОТПРАВЛЕННОЕ сообщение.

    Возвращает (campaign_id, message_id). Поля входных структур — РЕАЛЬНЫЕ
    сигнатуры store.py (как в остальных тестах проекта).
    """
    from datetime import datetime, timedelta, timezone

    from sender.store import CampaignIn, MessageIn, RecipientIn, SequenceStepIn

    rid = store.upsert_recipient(RecipientIn(
        email="user@example.com", domain="example.com", company_name="User"))
    cid = store.create_campaign(CampaignIn(
        name="c1", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, subject_tmpl="Sub", body_tmpl="Body",
        delay_hours=0))
    mid, _created = store.enqueue_message(MessageIn(
        idempotency_key="wiring-1", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=datetime.now(timezone.utc)))
    # Отправлено «давно»: префетч-отсев (min_age_sec) не мешает тестам,
    # спать в тестах не нужно.
    store.mark_sent(mid, "<rfc-wiring@id>",
                    datetime.now(timezone.utc) - timedelta(seconds=60))
    return cid, mid


def test_pixel_valid_token_records_open(server, config, store):
    """GET /o/<валидный токен старого письма> -> 200 + GIF, событие open одно."""
    from sender.tracking import GIF_PIXEL, OpenTracker

    _srv, base = server
    cid, mid = _seed_sent_message(store)

    tracker = OpenTracker(config, store)
    token = _open_token(tracker, mid)


    status, body, headers = _get(base, f"/o/{token}")

    assert status == 200
    assert body == GIF_PIXEL
    assert "image/gif" in headers.get("Content-Type", "")
    # Кэш выключен: провайдеры/клиенты не должны переиспользовать ответ.
    assert "no-store" in headers.get("Cache-Control", "")

    from sender.analytics import Analytics

    assert Analytics(store).campaign_report(cid).opens == 1


def test_pixel_garbage_token_still_gif_no_event(server, store):
    """GET /o/мусор -> ТОЖЕ 200 + GIF, но open-событий не появилось."""
    from sender.analytics import Analytics
    from sender.tracking import GIF_PIXEL

    _srv, base = server

    status, body, headers = _get(base, "/o/not-a-real-token")

    # На битый токен отдаём тот же прозрачный GIF, чтобы не палить трекинг.
    assert status == 200
    assert body == GIF_PIXEL
    assert "image/gif" in headers.get("Content-Type", "")

    assert Analytics(store).global_report().total_opens == 0


def test_health_endpoint_ok(server):
    """GET /health -> 200 ok: роут отписки/здоровья не сломан пикселем."""
    _srv, base = server

    status, body, _headers = _get(base, "/health")

    assert status == 200
    assert b"ok" in body.lower()


def test_build_mime_with_and_without_pixel(config, store, suppression):
    """_build_mime: pixel_url делает письмо multipart/alternative с <img>."""
    from sender.gates import Gates
    from sender.sender import Sender

    gates = Gates(config, store)
    sender = Sender(config, store, suppression, gates, dry_run=True)

    headers = {
        "From": "Sender <box1@example.com>",
        "To": "user@example.com",
        "Subject": "Привет",
    }
    # Минимальный RenderedMessage: собираем через SimpleNamespace, чтобы не
    # зависеть от конструктора sender.personalize.
    rendered = SimpleNamespace(
        subject="Привет",
        body="Текст письма",
        unfilled_fields=[],
    )

    pixel_url = "https://t.example/o/tok"
    # _build_mime сразу возвращает bytes (EmailMessage.as_bytes внутри).
    raw_with = sender._build_mime(headers, rendered, pixel_url=pixel_url)

    # С пикселем — HTML-часть в multipart/alternative и ссылка на пиксель.
    assert b"multipart/alternative" in raw_with
    assert pixel_url.encode("utf-8") in raw_with

    raw_without = sender._build_mime(headers, rendered)

    # Без пикселя — обычный text/plain, никакого <img>.
    assert b"text/plain" in raw_without
    assert b"<img" not in raw_without
    assert b"multipart/alternative" not in raw_without


def test_analytics_counts_open_gates_ignore(config, store):
    """Open учитывается в отчётах, но НЕ триггерит глобальные гейты."""
    from sender.analytics import Analytics
    from sender.gates import Gates
    from sender.tracking import OpenTracker

    cid, mid = _seed_sent_message(store)

    # open_rate = opens/sent: mark_sent меняет статус письма, но событие 'sent'
    # в журнал пишет боевой Sender.send — здесь добавляем его руками.
    from datetime import datetime, timezone

    from sender.store import EventIn

    store.append_event(EventIn(
        dedup_key=f"send:{mid}", event_type="sent",
        event_ts=datetime.now(timezone.utc), message_id=mid, campaign_id=cid))

    tracker = OpenTracker(config, store)
    token = _open_token(tracker, mid)
    # Возраст письма > 3 сек (сид шлёт «минуту назад»), префетч-отсев молчит.
    tracker.record_open(token)

    analytics = Analytics(store)
    report = analytics.campaign_report(cid)
    assert report.opens == 1
    # sent == 1 в журнале, значит доля открытий > 0.
    assert report.open_rate > 0

    assert analytics.global_report().total_opens == 1

    # Гейты считают отказы/жалобы, но не открытия: тревога не должна сработать.
    assert Gates(config, store).check_global().tripped is False
