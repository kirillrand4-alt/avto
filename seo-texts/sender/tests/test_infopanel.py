"""Задача 2 MUST: инфо-панель оператора — все 10 блоков + SHOULD.

Юниты на синтетике (снапшот enrich.db в тестах не нужен): каждый MUST-блок
из ТЗ ENGINEER-TASKS-CONFIRM-SEND проверяется отдельно.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.infopanel import build_panel, classify_contact_source  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402
from sender import snyatye  # noqa: E402

UTC = timezone.utc

COMPANY = {
    "inn": "3662065051", "name": "ООО «ЭФКО Пищевые Ингредиенты»",
    "division": "kc", "okved": "10.41", "region": "Воронежская обл.",
    "site": "https://efko.ru", "activity": "производство масложировой продукции",
    "is_competitor": 0, "verified": "inn",
}
EMAILS = [
    {"email": "zakupki@efko.ru", "role": "снабжение/закупки",
     "person": "Иванов Пётр", "mx_ok": 1, "source": "site",
     "updated_at": "2026-07-01"},
    {"email": "info@efko.ru", "role": "общий", "person": "", "mx_ok": 1,
     "source": "site", "updated_at": "2026-01-10"},
]
SIGNALS = [
    {"source": "news", "event_type": "модернизация",
     "what": "модернизация линии рафинации, заём ФРП",
     "sum": "300 млн руб.", "source_url": "https://example.com/news/1",
     "hotness": 5, "ts": "2026-07-10", "updated_at": "2026-07-10"},
    {"source": "news", "event_type": "инвестиции", "what": "новый цех",
     "sum": "", "source_url": "https://example.com/news/2", "hotness": 3,
     "ts": "2026-05-01", "updated_at": "2026-05-01"},
]
BASE = {"revenue": 2.5e9, "director": "Иванов Пётр Сергеевич"}

LETTER_OK = (
    "Здравствуйте, Пётр!\n\n"
    "Видели новость про модернизацию линии — под такой проект обычно нужен "
    "надёжный сжатый воздух. В Воронежская обл. у нас 3 внедрения.\n"
    "Винтовой компрессор обойдётся от 1 200 000 руб.\n\n"
    "--\nООО «Руспром», ИНН 2221239841, prokompressor.ru\n"
    "Если письма не нужны — ответьте «отписаться»."
)


def panel(**kw):
    args = dict(inn="3662065051", email="zakupki@efko.ru",
                letter_subject="Сжатый воздух под модернизацию",
                letter_body=LETTER_OK, company=COMPANY, emails=EMAILS,
                signals=SIGNALS, base=BASE)
    args.update(kw)
    return build_panel(**args)


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "p.db"))
    s.init_schema()
    yield s
    s.close()


# -- MUST 1: стоп-флаги ------------------------------------------------------- #
def test_no_flags_on_clean_lead():
    p = panel()
    assert p["stop_flags"] == []
    assert p["actions"]["confirm_hold"] is False


def test_flag_competitor_and_mismatch():
    p = panel(company={**COMPANY, "is_competitor": 1, "verified": "mismatch"})
    codes = [f["code"] for f in p["stop_flags"]]
    assert "competitor" in codes and "site_mismatch" in codes
    assert p["actions"]["confirm_hold"] is True  # «Отправить» требует hold


def test_flag_dead_mx():
    ems = [{**EMAILS[0], "mx_ok": 0}]
    p = panel(emails=ems)
    assert any(f["code"] == "mx_dead" for f in p["stop_flags"])


def test_flag_discontinued_series():
    p = panel(letter_body=LETTER_OK + "\nПредложим также Fini TERA110.")
    flags = [f for f in p["stop_flags"] if f["code"] == "discontinued_series"]
    assert flags and "TERA110" in flags[0]["label"]


def test_flag_suppressed_and_recent_contact(store):
    Suppression(store).add_email("zakupki@efko.ru", "unsubscribe")
    store.send_log_add(email="zakupki@efko.ru", outcome="sent",
                       ts=datetime.now(UTC) - timedelta(days=10))
    p = panel(store=store)
    codes = [f["code"] for f in p["stop_flags"]]
    assert "suppressed" in codes and "recent_contact" in codes


# -- MUST 2: скоринг-шапка ----------------------------------------------------- #
def test_scoring_components_and_badges():
    p = panel()
    s = p["scoring"]
    # сигнал 12 дн → 40п, выручка 2.5 млрд → 20п, verified inn → 15п,
    # роль снабжение → 15п = 90 (максимум)
    assert s["parts"] == {"signal": 40, "signal_max": 40,
                          "revenue": 20, "revenue_max": 20,
                          "verified": 15, "verified_max": 15,
                          "role": 15, "role_max": 15}
    assert s["score"] == 90 and s["color"] == "green"
    assert s["buying_power"] == "large"  # 2.5 млрд < 5e9; бюджет 10.41=3 без сдвига
    assert s["capex_badge"].startswith("🔥")
    assert s["budget_confirmed"] == "фрп"


def test_scoring_grey_without_anything():
    p = panel(company={"inn": "1", "okved": ""}, emails=[], signals=[], base={})
    assert p["scoring"]["score"] == 0 and p["scoring"]["color"] == "grey"
    assert p["scoring"]["capex_badge"] == "нет триггера"


# -- MUST 3: карточка повода ---------------------------------------------------- #
def test_signal_card_top_and_others():
    p = panel()
    sig = p["signal"]
    assert sig["present"] and sig["top"]["event_type"] == "модернизация"
    assert sig["top"]["source_url"].startswith("https://")
    assert sig["top"]["stars"] == "★★★★★"
    assert sig["top"]["date"] == "2026-07-10"
    assert len(sig["others"]) == 1


def test_signal_absent_is_honest_cold():
    p = panel(signals=[])
    assert p["signal"] == {"present": False,
                           "label": "повода нет — холодный заход"}


# -- MUST 4: контакт ------------------------------------------------------------ #
def test_contact_lpr_match_and_role():
    p = panel()
    c = p["contact"]
    assert c["role"] == "снабжение/закупки" and c["router"] is False
    assert c["lpr"] == "match"           # Иванов Пётр == директор Иванов Пётр С.
    assert c["mx_ok"] is True
    assert c["verified_icons"] == "ИНН✅"
    assert c["domain_mismatch"] is False


def test_contact_router_and_domain_mismatch():
    ems = [{"email": "info@mail.ru", "role": "приёмная", "person": "",
            "mx_ok": 1, "source": "", "updated_at": ""}]
    p = panel(email="info@mail.ru", emails=ems)
    c = p["contact"]
    assert c["router"] is True
    assert c["domain_mismatch"] is True   # mail.ru != efko.ru
    assert c["lpr"] == "impersonal"


# -- MUST 4b: ЧЕСТНЫЙ провенанс контакта ---------------------------------------- #
#
# Баг 27.07 (владелец, скриншот карточки очереди): «откуда знаем: подтверждено
# разбором сайта» при ПУСТОМ поле «сайт», а «чем занимается» описывало чужую
# организацию (АО «РСП ЧЕРМК-ЮГ», ИНН 3528036219, ОКВЭД 64.20 → в карточке
# «справочные правовые системы КонсультантПлюс»). Панель печатала в строке
# источника КОНТАКТА поле companies.verified, которое описывает САЙТ.

# компания того же вида, что в баге: привязка сайта в verified осталась,
# самого сайта в карточке нет
NO_SITE = {**COMPANY, "site": "", "verified": "provider",
           "activity": "разработка и сопровождение справочных правовых систем"}


def test_source_classifier_vocabulary():
    """Разбор реальных значений emails.source серверного обогащения."""
    assert classify_contact_source("own-site:staff")["kind"] == "site"
    assert classify_contact_source("own-site")["kind"] == "site"
    assert classify_contact_source("egrul:dadata")["kind"] == "egrul"
    assert classify_contact_source("zakupki:eis")["kind"] == "zakupki"
    assert classify_contact_source("news")["kind"] == "news"
    assert classify_contact_source("сайт (база)")["kind"] == "site"
    assert classify_contact_source("база")["kind"] == "obzvon"
    # донор phone-match — чужой ИНН, оператор должен видеть это в тексте
    pm = classify_contact_source("phone-match:7707049388")
    assert pm["kind"] == "phone_match" and "7707049388" in pm["label"]
    # ничего не выдумываем
    assert classify_contact_source("")["kind"] == "unknown"
    assert classify_contact_source("")["label"] == "источник не зафиксирован"


def test_provenance_never_claims_site_without_site():
    """Главный регресс: без подтверждённого сайта — никакого «с сайта»."""
    ems = [{**EMAILS[0], "source": "own-site", "source_url": ""}]
    c = panel(company=NO_SITE, emails=ems)["contact"]
    assert c["provenance_conflict"] is True
    assert c["provenance_trusted"] is False
    assert "сайта в карточке нет" in c["provenance"]
    assert "подтверждено разбором сайта" not in c["provenance"]
    assert c["source_kind"] == "site"    # канал как в БД, врёт не он
    # verified остался от старой привязки — иконку гасим и помечаем протухшей
    assert c["site_confirmed"] is False
    assert c["site_verified_stale"] is True
    assert c["verified_icons"] == "—"
    assert c["verified_scope"] == "site"
    # ссылки взяться неоткуда — и мы её не сочиняем
    assert c["source_link"] == "" and c["source_link_kind"] == "none"


def test_provenance_site_present_but_unconfirmed_is_not_a_conflict():
    """Сайт есть, привязка не подтверждена (или verified не долетел, как при
    пересборке блока в api/app.py) — это «не подтверждено», а не «сайта нет»."""
    ems = [{**EMAILS[0], "source": "own-site", "source_url": ""}]
    c = panel(company={**COMPANY, "verified": ""}, emails=ems)["contact"]
    assert c["provenance_conflict"] is False    # ложной тревоги нет
    assert c["provenance_trusted"] is False     # но и «подтверждено» не пишем
    assert "не подтверждена" in c["provenance"]
    assert c["source_link"] == "https://efko.ru"   # ссылка всё равно есть


def test_provenance_site_mismatch_is_a_conflict():
    ems = [{**EMAILS[0], "source": "own-site", "source_url": ""}]
    c = panel(company={**COMPANY, "verified": "mismatch"}, emails=ems)["contact"]
    assert c["provenance_conflict"] is True
    assert "ДРУГОЙ компании" in c["provenance"]
    assert c["verified_icons"] == "❌сайт не тот"   # mismatch показываем всегда


def test_provenance_reflects_real_source_not_verified():
    """Контакт из ЕИС в компании с verified=provider: источник — ЕИС, не сайт."""
    ems = [{**EMAILS[0], "source": "zakupki:eis",
            "source_url": "https://zakupki.gov.ru/223/purchase/view/1"}]
    c = panel(emails=ems)["contact"]
    assert c["source_kind"] == "zakupki"
    assert c["provenance"] == "карточка закупки в ЕИС"
    assert c["provenance_conflict"] is False
    assert c["source_link"] == "https://zakupki.gov.ru/223/purchase/view/1"
    assert c["source_link_kind"] == "page"


def test_provenance_unknown_source_is_honest():
    ems = [{**EMAILS[0], "source": "", "source_url": ""}]
    c = panel(emails=ems)["contact"]
    assert c["source_kind"] == "unknown"
    assert c["provenance"] == "источник не зафиксирован"
    assert c["provenance_trusted"] is False


# -- владелец: «сделать контакты кликабельными ссылками на их источник» -------- #
def test_source_link_falls_back_to_confirmed_site_domain():
    """Точной страницы нет, но сайт подтверждён — отдаём хотя бы домен."""
    ems = [{**EMAILS[0], "source": "own-site", "source_url": ""}]
    c = panel(emails=ems)["contact"]
    assert c["source_link"] == "https://efko.ru"
    assert c["source_link_kind"] == "domain"
    assert c["source_url"] == ""          # сырое поле не подменяем


def test_source_link_normalizes_bare_domain_and_drops_junk():
    bare = [{**EMAILS[0], "source": "news", "source_url": "vedomosti.ru/a/1"}]
    assert panel(emails=bare)["contact"]["source_link"] == \
        "https://vedomosti.ru/a/1"
    junk = [{**EMAILS[0], "source": "news", "source_url": "не указано"}]
    c = panel(emails=junk)["contact"]
    assert c["source_link"] == "" and c["source_link_kind"] == "none"


def test_flat_emails_list_carries_own_provenance():
    """Селект «сменить email»: у каждого адреса СВОЙ канал и СВОЯ ссылка."""
    ems = [
        {**EMAILS[0], "source": "zakupki:eis",
         "source_url": "https://zakupki.gov.ru/x"},
        {**EMAILS[1], "source": "egrul:dadata", "source_url": ""},
    ]
    by_addr = {e["email"]: e for e in panel(emails=ems)["emails"]}
    assert by_addr["zakupki@efko.ru"]["source_kind"] == "zakupki"
    assert by_addr["zakupki@efko.ru"]["source_link"] == "https://zakupki.gov.ru/x"
    assert by_addr["info@efko.ru"]["source_kind"] == "egrul"
    assert by_addr["info@efko.ru"]["provenance"] == "ЕГРЮЛ, открытый реестр"


# -- «чем занимается» без подтверждённого сайта = НЕ ПРОВЕРЕНО ----------------- #
def test_activity_unverified_without_site():
    comp = panel(company=NO_SITE)["company"]
    assert comp["activity"].startswith("разработка")   # значение НЕ удалено
    assert comp["activity_verified"] is False
    assert "НЕ ПРОВЕРЕНО" in comp["activity_note"]
    assert comp["activity_source"] == ""


def test_activity_verified_with_confirmed_site():
    comp = panel()["company"]
    assert comp["activity_verified"] is True
    assert comp["activity_source"] == "разбор сайта efko.ru"
    assert comp["activity_note"] == ""


def test_activity_flags_absent_when_no_activity():
    comp = panel(company={**COMPANY, "activity": ""})["company"]
    assert comp["activity_verified"] is False and comp["activity_note"] == ""


def test_activity_unverified_when_site_mismatch():
    """verified=mismatch — сайт чужой, описание с него доверять нельзя."""
    comp = panel(company={**COMPANY, "verified": "mismatch"})["company"]
    assert comp["activity_verified"] is False and comp["activity_note"]


# -- MUST 5: компания-снипет ------------------------------------------------------ #
def test_company_snippet_why_equipment():
    p = panel()
    comp = p["company"]
    assert comp["name"].startswith("ООО")
    assert comp["revenue_h"] == "2.5 млрд ₽"
    assert comp["division"] == "kc" and comp["division_badge"] == "КЦ"
    assert "сжатый воздух" in comp["why_equipment"]
    # Род деятельности БОЛЬШЕ не вклеивается в «зачем оборудование»: склеенные
    # в одну строку, они читались как одно утверждение. Теперь деятельность —
    # своя строка карточки, а «вывод по» показывает основание (ОКВЭД).
    assert "масложировой" in comp["activity"]
    assert comp["why_basis"] == "ОКВЭД 10.41"


# -- MUST 6: письмо + подсветка ---------------------------------------------------- #
def test_letter_highlights():
    p = panel()
    kinds = {h["kind"] for h in p["letter"]["highlights"]}
    texts = " | ".join(h["text"] for h in p["letter"]["highlights"])
    assert "name" in kinds and "Пётр" in texts
    assert "price" in kinds
    assert "trigger" in kinds  # «модернизация»


# -- MUST 7: KB-провенанс ----------------------------------------------------------- #
def test_kb_provenance_overclaim_yellow():
    kb_ctx = {"cases": [{"id": "k1", "city": "Воронеж", "what": "компрессорная"}],
              "geo": "в регионе у нас 2 реализованных проектов",
              "price_band": "1-2 млн", "budget_score": 3,
              "signal_hint": "событие свежее — срочный тон"}
    p = panel(kb_ctx=kb_ctx)  # письмо заявляет 3 внедрения, факт KB = 2
    kb = p["kb"]
    assert kb["geo_fact"] == 2 and kb["geo_claimed"] == 3
    assert kb["geo_overclaim"] is True
    assert kb["trigger_confirmed"] is True  # signals есть
    assert kb["cases"][0]["city"] == "Воронеж"


def test_kb_no_overclaim_when_honest():
    kb_ctx = {"cases": [], "geo": "в регионе у нас 5 реализованных проектов",
              "signal_hint": ""}
    p = panel(kb_ctx=kb_ctx)
    assert p["kb"]["geo_overclaim"] is False
    assert p["kb"]["trigger_confirmed"] is None  # фразы нет — нечего сверять


# -- MUST 8: комплаенс ФЗ-38/152 ------------------------------------------------------ #
def test_compliance_ok_letter():
    p = panel()
    c = p["compliance"]
    assert c["attribution_ok"] is True
    assert c["unsub_in_body"] is True
    assert c["fio_scale"] in ("0", "1")  # «Иванов Пётр Сергеевич» нет в письме


def test_compliance_catches_violations():
    bad = "Мы лучшие и №1, дешевле чем у всех! Директор Иванов Пётр Сергеевич."
    p = panel(letter_body=bad)
    c = p["compliance"]
    assert c["attribution_ok"] is False       # нет ООО «Руспром» + ИНН
    assert c["unsub_in_body"] is False and c["unsub_note"]
    assert c["fio_count"] >= 1
    assert any("лучш" in b.lower() for b in c["banned_phrases"])
    assert any("№" in b for b in c["banned_phrases"])


# -- MUST 9: панель действий ----------------------------------------------------------- #
def test_actions_hotkeys():
    p = panel()
    assert p["actions"]["hotkeys"] == {"Enter": "approve", "E": "edit",
                                       "S": "skip", "X": "stoplist"}


# -- MUST 10: история контактов --------------------------------------------------------- #
def test_history_feed_and_recent_flag(store):
    store.send_log_add(email="zakupki@efko.ru", inn="3662065051",
                       subject="Прошлое письмо", outcome="sent",
                       ts=datetime.now(UTC) - timedelta(days=40))
    store.send_log_add(email="zakupki@efko.ru", outcome="replied",
                       ts=datetime.now(UTC) - timedelta(days=38))
    p = panel(store=store)
    h = p["history"]
    assert len(h["items"]) == 2
    assert h["recent_90d"] is True          # красный флаг <90 дн
    assert h["replied_before"] is True
    assert h["last"]["subject"] == "Прошлое письмо"


def test_history_without_store_is_honest():
    p = panel(store=None)
    assert p["history"]["note"] == "send_log недоступен"


# -- честные пропуски -------------------------------------------------------------------- #
def test_reserved_catch_all_not_checked():
    p = panel()
    assert "не проверялось" in p["reserved"]["catch_all"]


# -- SHOULD ------------------------------------------------------------------------------- #
def test_should_deliverability_and_age():
    p = panel()
    sh = p["should"]
    assert sh["deliverability"]["light"] == "green"
    assert sh["okved_matched"] == ["10.41"]
    assert sh["legal_basis"] == "публичный адрес с сайта компании"
    assert sh["contact_age_days"] is not None


def test_should_yellow_free_provider_and_price_gap():
    ems = [{"email": "zakaz@mail.ru", "role": "общий", "person": "",
            "mx_ok": 1, "source": "", "updated_at": ""}]
    body = "Компрессорная станция под ключ — 12 000 000 руб."
    p = panel(email="zakaz@mail.ru", emails=ems, base={}, letter_body=body)
    sh = p["should"]
    assert sh["deliverability"]["light"] == "yellow"
    assert sh["free_provider"] is True
    assert sh["price_gap"] is True   # micro-компания, прайс 12 млн


def test_legal_basis_does_not_claim_site_without_site():
    """ФЗ-152: «публичный адрес с сайта» — только при подтверждённом сайте."""
    ems = [{**EMAILS[0], "source": "own-site", "source_url": ""}]
    assert panel(company=NO_SITE, emails=ems)["should"]["legal_basis"] == \
        "источник записан как сайт компании, но сайт не подтверждён"


def test_legal_basis_by_real_channel():
    ems = [{**EMAILS[0], "source": "egrul:dadata"}]
    assert panel(emails=ems)["should"]["legal_basis"] == "ЕГРЮЛ/открытый реестр"
    ems = [{**EMAILS[0], "source": "zakupki:eis"}]
    assert panel(emails=ems)["should"]["legal_basis"] == \
        "источник: карточка закупки в ЕИС"
    ems = [{**EMAILS[0], "source": ""}]
    assert panel(emails=ems)["should"]["legal_basis"] == \
        "источник адреса не зафиксирован"


def test_should_domain_concentration():
    p = panel(batch_domains={"efko.ru": 4})
    assert p["should"]["domain_concentration"] == 4


# -- snyatye: подключение в QA-гейт автоответчика ------------------------------------------ #
def test_snyatye_hard_stop_is_17():
    assert len(snyatye.stop_series()) == 17


def test_qa_reply_catches_discontinued_series():
    from sender.autoresponder import qa_reply
    problems = qa_reply("Re: компрессор",
                        "Здравствуйте! Предлагаем Fini TERA160 со склада.\n"
                        "С уважением, менеджер ООО «Руспром»")
    assert any("снятая с производства" in p for p in problems)
