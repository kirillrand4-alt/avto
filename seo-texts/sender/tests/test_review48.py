# -*- coding: utf-8 -*-
"""Ревью #48 (26.07): свежие дефекты кода панели, найденные полным проходом.

Каждый тест здесь падал КРАСНЫМ на до-фиксном коде (проверено через git stash):
  1. confirm._audit_force звал неопределённый logger — сбой записи аудита
     ронял force-отправку NameError'ом вместо письма;
  2. выбор ящика оператором (panel.mailbox_id) игнорировался для ИСХОДЯЩИХ:
     карточка показывала «с ящика X (оператор)», а слал pick_mailbox со своего;
  3. перегенерация письма (#71) собирала panel_json заново и молча теряла
     выбранный оператором ящик;
  4. approve/edit разрешались, пока письмо перегенерируется в фоне — могла
     уйти версия текста, которую оператор не видел;
  5. AiQuota без конфига (юнит-тесты) считал идеи-линзы включёнными и жёг
     реальные вызовы провайдера прямо из pytest (~45 с и деньги на письмо).
"""

import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.confirm import ConfirmSend  # noqa: E402
from sender.dtos import (  # noqa: E402
    CampaignIn, MailboxState, MessageIn, RecipientIn, SequenceStepIn,
)
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402
from sender.tests.test_confirm_live import (  # noqa: E402
    _Cfg, _Gates, _LiveOpener, _seed, _submit,
)
from sender.sender import Sender  # noqa: E402

UTC = timezone.utc


@pytest.fixture
def config(tmp_path):
    for i in range(1, 6):
        os.environ[f"BOX{i}_PASSWORD"] = "secret"
    os.environ["UNSUB_SIGNING_SECRET"] = "test_secret_key_min_32_chars_long"
    path = tmp_path / "c.yaml"
    path.write_text(BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "t.db")),
                    encoding="utf-8")
    return Config.load(str(path))


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    s.init_schema()
    yield s
    s.close()


def _live_sender(config, store, suppression):
    sndr = Sender(config, store, suppression, _Gates(), dry_run=False)
    opener = _LiveOpener()
    sndr._smtp_opener = opener
    return sndr, opener


# --------------------------------------------------------------------------- #
# 1. Сбой аудита не должен ронять force-отправку (NameError: logger)
# --------------------------------------------------------------------------- #
def test_force_send_survives_audit_failure(config, store, monkeypatch):
    supp = Suppression(store)
    supp.add_email("lead@zavod.ru", "manual")     # заслон, который обходим
    sndr, opener = _live_sender(config, store, supp)
    cs = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp,
                     sender=sndr)
    cid, rid, mid = _seed(store)
    # allow_suppressed: тест про то, что сбой аудита не рвёт force-отправку,
    # а не про попадание в очередь. С 17.08 confirm_submit сам переводит
    # адресата из стоп-листа в 'skipped' — здесь строка нужна живой, чтобы
    # оператору было что обходить силой.
    review_id, _ = store.confirm_submit(
        email="lead@zavod.ru", inn="4201000625", campaign_id=cid,
        recipient_id=rid, message_id=mid, subject="s", body="b",
        status="pending", allow_suppressed=True)

    def _boom(**kw):
        raise RuntimeError("audit db locked")

    monkeypatch.setattr(store, "append_audit", _boom)
    # до фикса: NameError (logger не определён) вместо отправки
    assert cs.approve(review_id, operator="op", force=True) is True
    assert len(opener.sent) == 1
    assert store.confirm_get(review_id)["status"] == "sent"


# --------------------------------------------------------------------------- #
# 2. Выбор ящика оператором уважается ИСХОДЯЩЕЙ отправкой
# --------------------------------------------------------------------------- #
def test_operator_mailbox_choice_wins_for_outbound(config, store):
    supp = Suppression(store)
    sndr, opener = _live_sender(config, store, supp)
    cs = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp,
                     sender=sndr)
    cid, rid, mid = _seed(store)                     # mx_provider=yandex
    review_id = _submit(cs, store, cid, rid, mid)
    # подбор по пулу выбрал бы box1/box2 (pool_yandex); оператор выбирает box3
    cs.set_mailbox(review_id, "box3@rusprom.ru", operator="op")

    assert cs.approve(review_id, operator="op") is True
    assert len(opener.sent) == 1
    frm = opener.sent[0][0]
    assert frm == "box3@rusprom.ru", (
        f"письмо ушло с {frm}, хотя оператор выбрал box3 — выбор в карточке "
        "не должен быть декорацией")
    # и залогинились именно в выбранный ящик
    assert ("login", "box3@rusprom.ru") in [
        c[:2] for c in opener.calls if c[0] == "login"]


def test_operator_mailbox_unavailable_falls_back(config, store):
    """Выбранный ящик встал на паузу ПОСЛЕ выбора — шлём как подбор (то же,
    что показывает send_as), а не с паузного ящика и не падаем."""
    supp = Suppression(store)
    sndr, opener = _live_sender(config, store, supp)
    cs = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp,
                     sender=sndr)
    cid, rid, mid = _seed(store)
    review_id = _submit(cs, store, cid, rid, mid)
    cs.set_mailbox(review_id, "box3@rusprom.ru", operator="op")
    store.set_mailbox_paused("box3@rusprom.ru", True, "тест")

    assert cs.approve(review_id, operator="op") is True
    assert opener.sent and opener.sent[0][0] != "box3@rusprom.ru"


# --------------------------------------------------------------------------- #
# 3. Перегенерация не теряет выбранный оператором ящик
# --------------------------------------------------------------------------- #
def _quota_with_letters(store):
    from sender.ai_quota import AiQuota
    from sender.tests.test_ai_quota import _FakeGen, TODAY

    cid = store.create_campaign(CampaignIn(
        name="новостные", legal_entity="ООО «Руспром»", legal_inn="2221239841",
        config={"segment": "новостные"}))
    store.add_step(SequenceStepIn(campaign_id=cid, step_index=0, delay_hours=0,
                                  subject_tmpl="{company_name}",
                                  body_tmpl="{news_object}"))
    for i in range(3):
        store.upsert_recipient(RecipientIn(
            email=f"lead{i}@zavod{i}.ru", domain=f"zavod{i}.ru",
            inn=f"770100000{i}", company_name=f"ООО «Завод {i}»",
            okved="25.62", segment="новостные"))
    gen = _FakeGen()
    q = AiQuota(store, db_path=store._db_path, gen_factory=lambda: gen,
                batch=4, today_fn=lambda: TODAY)
    q.set_schedule(cid, {TODAY: 2})
    q.run_today(cid)
    return q, cid


def test_regenerate_preserves_operator_mailbox(store):
    q, cid = _quota_with_letters(store)
    row = store.confirm_list(status="pending", campaign_id=cid, limit=5)[0]
    # оператор выбрал ящик в карточке (ConfirmSend.set_mailbox пишет сюда же)
    store.confirm_set_panel(row["id"], {"mailbox_id": "box1@rusprom.ru"})

    out = q.regenerate_review(row["id"])
    assert out["ok"] is True

    fresh = store.confirm_get(row["id"])
    assert fresh["panel"].get("ai") is True          # панель собрана заново
    assert fresh["panel"].get("mailbox_id") == "box1@rusprom.ru", (
        "перегенерация текста сбросила выбор ящика оператора")


# --------------------------------------------------------------------------- #
# 5. Идеи-линзы не ходят в провайдера, когда AiQuota собран без конфига
# --------------------------------------------------------------------------- #
def test_ideas_do_not_call_provider_without_config(store, monkeypatch):
    from sender.ai_quota import AiQuota

    calls = []

    def _spy(*a, **kw):
        calls.append(a)
        raise AssertionError("сеть из юнит-теста")

    import gen_provider
    monkeypatch.setattr(gen_provider, "call", _spy)

    q = AiQuota(store, db_path=store._db_path)       # config=None, как в тестах
    reqs = [{"company_name": "ООО", "okved": "25", "activity": "", "extra": {}}]
    q._add_ideas_generic(reqs)
    assert calls == [], (
        "AiQuota без конфига пошёл в провайдера — pytest жёг бы деньги "
        "владельца на каждом GENERIC-письме")
