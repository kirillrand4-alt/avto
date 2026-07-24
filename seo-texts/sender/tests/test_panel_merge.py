"""§3 BASE-MERGE: панель — все новости со ссылками, полная карточка,
контракт news_object/city (очередь «дозаполнить данные»)."""

import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.company_card import ObzvonIndex, build_company_card  # noqa: E402
from sender.confirm_cli import render_panel_text  # noqa: E402
from sender.infopanel import build_panel  # noqa: E402
from sender.tests.test_company_card import (  # noqa: E402
    _build_index, _make_enrich,
)

UTC = timezone.utc


def _card(tmp_path):
    db, _ = _build_index(tmp_path)
    enrich = _make_enrich(tmp_path)
    return build_company_card("4201000625", obzvon=ObzvonIndex(db),
                              enrich_db_path=enrich)


def _signals():
    return [
        {"source": "news", "event_type": "modernization",
         "what": "ООО Кузбасский Завод модернизирует цех",
         "news_object": "цех", "sum": "120 млн",
         "source_url": "https://news.ru/zavod-ceh", "hotness": 8,
         "ts": "2026-07-15"},
        {"source": "rss", "event_type": "expansion",
         "what": "Новая линия в регионе",  # имени компании нет
         "sum": "", "source_url": "https://rss.ru/line", "hotness": 3,
         "ts": "2026-07-10"},
    ]


def test_news_events_all_with_links_and_match(tmp_path):
    card = _card(tmp_path)
    panel = build_panel(inn="4201000625", email="a@zavod.ru",
                        letter_subject="s", letter_body="b",
                        signals=_signals(), card=card)
    ne = panel["news_events"]
    assert ne["count"] == 2                      # ВСЕ события, не только топ
    assert ne["events"][0]["hotness"] == 8       # горячее первым
    assert all(e["source_url"] for e in ne["events"])
    assert ne["events"][0]["match_ok"] is True   # «Завод» найден в тексте
    assert ne["events"][0]["signal_match"] == "имя в тексте"
    assert ne["events"][1]["match_ok"] is False  # чужая новость — жёлтый флаг
    assert "проверь" in ne["events"][1]["signal_match"]


def test_company_full_block(tmp_path):
    card = _card(tmp_path)
    panel = build_panel(inn="4201000625", email="a@zavod.ru",
                        letter_subject="s", letter_body="b", card=card)
    cf = panel["company_full"]
    assert cf["available"] and cf["in_obzvon"]
    assert cf["division"] == "kc"                # только из базы обзвона
    assert cf["division_guess"] == "meyer"       # enrich — лишь предположение
    assert cf["reg"]["director"] == "Иванов Пётр Сидорович"
    assert cf["product"]["equip_categories"] == "Компрессоры | Осушители"
    emails = cf["contacts"]["emails"]
    assert emails[0]["origin"] == "enrich"
    assert emails[0]["source_url"].startswith("https://")
    phone_sources = {p["source"] for p in cf["contacts"]["phones"]}
    assert {"база", "сайт, с доб."} <= phone_sources


def test_panel_without_card_backcompat():
    panel = build_panel(inn="1", email="a@b.ru", letter_subject="s",
                        letter_body="b")
    assert panel["company_full"] == {"available": False}
    assert panel["news_events"]["count"] == 0


def test_cli_renders_new_blocks(tmp_path):
    card = _card(tmp_path)
    panel = build_panel(inn="4201000625", email="a@zavod.ru",
                        letter_subject="Тема", letter_body="Текст",
                        signals=_signals(), card=card)
    text = render_panel_text({"id": 1, "status": "pending",
                              "email": "a@zavod.ru", "inn": "4201000625",
                              "subject": "Тема", "body": "Текст",
                              "panel": panel})
    assert "НОВОСТНЫЕ СОБЫТИЯ (2)" in text
    assert "https://news.ru/zavod-ceh" in text   # ссылка присутствует
    assert "НЕТ имени — проверь" in text         # жёлтый флаг
    assert "ПОЛНАЯ КАРТОЧКА" in text
    assert "направление: kc" in text


def test_needs_data_queue(tmp_path):
    """Контракт: пустые обязательные поля → очередь «дозаполнить данные»."""
    from sender.dtos import CampaignIn, MessageIn, RecipientIn, SequenceStepIn
    from sender.store import Store
    s = Store(str(tmp_path / "n.db"))
    s.init_schema()
    cid = s.create_campaign(CampaignIn(
        name="news", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    sid = s.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="{news_object}", body_tmpl="{city}"))
    rid = s.upsert_recipient(RecipientIn(
        email="x@y.ru", domain="y.ru", inn="123", company_name="ООО Тест"))
    mid, _ = s.enqueue_message(MessageIn(
        idempotency_key="nd1", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=datetime.now(UTC)))
    s.mark_needs_data(mid, "unfilled_placeholders:news_object,city")
    msg = s.get_message(mid)
    assert msg.status == "needs_data"
    rows = s.list_needs_data()
    assert rows[0]["id"] == mid
    assert "news_object" in rows[0]["last_error"]
    assert rows[0]["email"] == "x@y.ru"
    # claim_due такие письма НЕ берёт
    claimed = s.claim_due_messages(now=datetime.now(UTC),
                                   mailbox_ids=["m@b.ru"], limit=10)
    assert all(m.id != mid for m in claimed)
    s.close()


def test_sender_routes_unfilled_to_needs_data(tmp_path):
    """sender.send шаг (1): unfilled → needs_data (не могила failed)."""
    from sender.errors import PersonalizationGateError
    from sender.sender import RenderedMessage, Sender
    from sender.suppression import Suppression
    from sender.store import Store
    from sender.dtos import CampaignIn, MessageIn, RecipientIn, SequenceStepIn
    from sender.tests.test_division_gate import _Gates, _Cfg  # noqa: F401
    from sender.tests.test_config import BASE_YAML
    from sender.config import Config
    for i in range(1, 6):
        os.environ[f"BOX{i}_PASSWORD"] = "secret"
    os.environ["UNSUB_SIGNING_SECRET"] = "test_secret_key_min_32_chars_long"
    yaml = BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "s.db"))
    (tmp_path / "c.yaml").write_text(yaml, encoding="utf-8")
    config = Config.load(str(tmp_path / "c.yaml"))
    s = Store(str(tmp_path / "s.db"))
    s.init_schema()
    cid = s.create_campaign(CampaignIn(
        name="n", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    sid = s.add_step(SequenceStepIn(campaign_id=cid, step_index=0,
                                    delay_hours=0, subject_tmpl="s",
                                    body_tmpl="b"))
    rid = s.upsert_recipient(RecipientIn(email="x@y.ru", domain="y.ru"))
    mid, _ = s.enqueue_message(MessageIn(
        idempotency_key="nd2", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=datetime.now(UTC)))
    sndr = Sender(config, s, Suppression(s), _Gates(), dry_run=True)
    with pytest.raises(PersonalizationGateError):
        sndr.send(s.get_message(mid),
                  RenderedMessage(subject="s", body="b",
                                  unfilled_fields=("news_object", "city")),
                  "box1@rusprom.ru", now=datetime.now(UTC))
    assert s.get_message(mid).status == "needs_data"
    s.close()
