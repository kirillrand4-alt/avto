"""API «Почта» (IMAP-браузер) + лента диалога через TestClient."""
import os
import sys
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.api.app import build_deps, make_app  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.mailbrowser import MailBrowser  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402
from sender.tests.test_mailbrowser import _FakeIMAP  # noqa: E402
from sender.dtos import (  # noqa: E402
    CampaignIn, EventIn, MessageIn, RecipientIn, SequenceStepIn,
)

UTC = timezone.utc


@pytest.fixture
def client(tmp_path):
    os.environ.update({f"BOX{i}_PASSWORD": "p" for i in range(1, 6)})
    os.environ["UNSUB_SIGNING_SECRET"] = "s" * 32
    (tmp_path / "c.yaml").write_text(
        BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "api.db")),
        encoding="utf-8")
    config = Config.load(str(tmp_path / "c.yaml"))
    store = Store(str(tmp_path / "api.db"))
    store.init_schema()
    deps = build_deps(config, store)
    deps.auth.create_user(username="owner", password="ownerpass", role="owner")
    # подменяем IMAP-браузер на фейковый (реального IMAP в тестах нет)
    deps.mailbrowser = MailBrowser(config, imap_opener=lambda mb: _FakeIMAP())
    app = make_app(deps)
    return TestClient(app), store, deps, config


def _tok(c):
    r = c.post("/auth/login",
               json={"username": "owner", "password": "ownerpass"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_mail_mailboxes_and_folders(client):
    c, _s, _d, config = client
    h = _tok(c)
    r = c.get("/mail/mailboxes", headers=h)
    assert r.status_code == 200
    assert len(r.json()["mailboxes"]) == len(config.mailboxes())
    mbid = config.mailboxes()[0].mailbox_id
    r = c.get(f"/mail/{mbid}/folders", headers=h)
    assert r.status_code == 200
    roles = {f["role"] for f in r.json()["folders"]}
    assert "inbox" in roles and "sent" in roles


def test_mail_messages_and_message(client):
    c, _s, _d, config = client
    h = _tok(c)
    mbid = config.mailboxes()[0].mailbox_id
    r = c.get(f"/mail/{mbid}/messages", headers=h, params={"folder": "INBOX"})
    assert r.status_code == 200
    assert r.json()["total"] == 3           # ВСЕ письма
    r = c.get(f"/mail/{mbid}/message", headers=h,
              params={"folder": "INBOX", "uid": "1"})
    assert r.status_code == 200
    assert "Текст письма." in r.json()["body"]


def test_mail_thread(client):
    c, _s, _d, config = client
    h = _tok(c)
    mbid = config.mailboxes()[0].mailbox_id
    r = c.get(f"/mail/{mbid}/thread", headers=h,
              params={"folder": "INBOX", "uid": "1"})
    uids = [m["uid"] for m in r.json()["thread"]]
    assert "1" in uids and "2" in uids and "3" not in uids


def test_mail_requires_auth(client):
    c, _s, _d, config = client
    mbid = config.mailboxes()[0].mailbox_id
    assert c.get(f"/mail/{mbid}/messages").status_code == 401


def test_contact_dialog_from_db(client):
    c, store, _d, _config = client
    h = _tok(c)
    cid = store.create_campaign(CampaignIn(
        name="c", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"))
    rid = store.upsert_recipient(RecipientIn(
        email="k@zavod.ru", domain="zavod.ru", inn="1"))
    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key="d1", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=datetime.now(UTC)))
    store.mark_sent(mid, "<out@box.ru>", datetime(2026, 7, 21, 10, tzinfo=UTC))
    # входящий ответ
    store.append_event(EventIn(
        dedup_key="in1", event_type="reply", event_ts=datetime(2026, 7, 21, 11, tzinfo=UTC),
        message_id=mid, recipient_id=rid, campaign_id=cid,
        mailbox_id="box1@rusprom.ru", provider="yandex",
        detail={"snippet": "Интересно, пришлите КП", "headers": {"Subject": "Re: s"}}))
    r = c.get(f"/dialog/{rid}", headers=h)
    assert r.status_code == 200
    thread = r.json()["thread"]
    assert len(thread) == 2
    assert thread[0]["direction"] == "out"       # исходящее раньше по времени
    assert thread[1]["direction"] == "in"
    assert "Интересно" in thread[1]["body"]
