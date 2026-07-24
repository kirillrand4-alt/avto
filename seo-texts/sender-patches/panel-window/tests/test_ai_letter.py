"""Тесты AI-генерации первого касания: механический гейт (без сети) + цикл
доработки с фейковым caller + анти-штамп + падежный гейт города."""

import json
import os
import sys

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.ai_letter import (  # noqa: E402
    AiLetterGen, gate, stamp_overflow, allowed_numbers, load_facts,
)

FACTS = {
    "total_crm": "больше 5580 внедрений по стране (CRM)",
    "published_site": "1018 опубликованных проектов на сайте",
    "region_counts_site_index": {"Барнаул": 78, "Москва": 69},
    "clients_verified": {},
}

GOOD_BODY = (
    "Добрый день!\n\n"
    "Попалась новость про линию розлива в Балашихе - обычно под такие проекты "
    "воздух считают еще на этапе проектирования.\n\n"
    "Я подбираю компрессорное оборудование в Компрессор Центре, у нас 78 "
    "опубликованных кейсов по Барнаулу.\n\n"
    "Подскажите, компрессорную уже заложили в проект, или всё решено - тогда "
    "и писать не стоит?\n\n"
    "С уважением,"
)


def test_gate_clean_letter_passes():
    fails = gate("вопрос по воздуху", GOOD_BODY, mode="NEWS",
                 extra={"news_object": "линия розлива", "city": "Балашиха"},
                 facts=FACTS)
    assert fails == [], fails


def test_gate_catches_stop_words_and_dash():
    body = GOOD_BODY.replace("Я подбираю", "Мы предлагаем — со скидкой")
    fails = gate("вопрос по воздуху", body, mode="NEWS",
                 extra={"city": "Балашиха"}, facts=FACTS)
    names = " | ".join(fails)
    assert "длинное тире" in names and "предлагаем" in names and "мы-корпоратив" in names


def test_gate_requires_optout_and_final():
    body = "Добрый день!\n\n" + "слово " * 60 + "\n\nБез финала и отказа."
    fails = gate("тема", body, facts=FACTS)
    names = " | ".join(fails)
    assert "нет опции отказа" in names and "финал не «С уважением,»" in names


def test_gate_numbers_must_be_allowed():
    body = GOOD_BODY.replace("78 опубликованных кейсов", "12345 клиентов")
    fails = gate("вопрос по воздуху", body, mode="NEWS",
                 extra={"city": "Балашиха"}, facts=FACTS)
    assert any("непроверенные числа" in f for f in fails)


def test_gate_subject_rules():
    fails = gate("Купите 5 компрессоров сейчас же обязательно!", GOOD_BODY,
                 mode="NEWS", extra={"city": "Балашиха"}, facts=FACTS)
    names = " | ".join(fails)
    assert "цифра в теме" in names and "знак ?/! в теме" in names


def test_gate_pseudo_news_only_generic():
    body = GOOD_BODY.replace(
        "Попалась новость про линию розлива в Балашихе",
        "Вижу, вы расширяете производство")
    generic = gate("вопрос по воздуху", body, mode="GENERIC", facts=FACTS)
    news = gate("вопрос по воздуху", body, mode="NEWS",
                extra={"city": "Балашиха"}, facts=FACTS)
    assert any("псевдо-новость" in f for f in generic)
    assert not any("псевдо-новость" in f for f in news)


def test_gate_city_declension():
    """Урок 2026-07-24: «в Санкт-Петербург» (именительный после «в») = брак."""
    body = GOOD_BODY.replace("в Балашихе", "в Санкт-Петербург")
    fails = gate("вопрос по воздуху", body, mode="NEWS",
                 extra={"news_object": "линия розлива", "city": "Санкт-Петербург"},
                 facts=FACTS)
    assert any("без склонения" in f for f in fails)
    # несклоняемый город («в Иваново») — не брак
    body2 = GOOD_BODY.replace("в Балашихе", "в Иваново")
    fails2 = gate("вопрос по воздуху", body2, mode="NEWS",
                  extra={"news_object": "линия розлива", "city": "Иваново"},
                  facts=FACTS)
    assert not any("без склонения" in f for f in fails2)


def test_stamp_overflow_scales():
    bodies = ["судя по профилю у вас линия"] * 3 + ["другое письмо"] * 2
    # лимит на 5 писем: round(4*5/49)=0 -> min 1; 3 вхождения > 1 => перебор
    over = stamp_overflow(bodies)
    assert any("судя по профилю" in o for o in over)


def test_allowed_numbers_includes_facts_and_extra():
    nums = allowed_numbers(FACTS, {"news_object": "цех на 4200 м2"})
    assert {"78", "69", "5580", "20", "4200"} <= nums


def test_load_facts_missing_file_fallback():
    f = load_facts("/nonexistent/kc-facts.json")
    assert "5580" in f["total_crm"]


# ------------------------------------------------------- цикл с фейком ---- #

def _fake_caller_factory(script):
    """script: список текстов-ответов по порядку вызовов."""
    calls = {"n": 0, "prompts": []}

    def caller(prompt):
        calls["prompts"].append(prompt)
        out = script[min(calls["n"], len(script) - 1)]
        calls["n"] += 1
        return out
    return caller, calls


BAD_LETTER = {"idx": 0, "subject": "предложение цены 555",
              "body": "Мы предлагаем скидку — купите!"}
GOOD_LETTER = {"idx": 0, "subject": "вопрос по воздуху", "body": GOOD_BODY}


def test_cycle_fix_round_repairs_letter():
    """1-й ответ — брак (гейт), fix-раунд возвращает чистое письмо."""
    caller, calls = _fake_caller_factory([
        json.dumps({"letters": [BAD_LETTER]}, ensure_ascii=False),
        json.dumps({"letters": [GOOD_LETTER]}, ensure_ascii=False),   # fix
        json.dumps({"verdicts": [{"idx": 0, "ok": True}]}),            # verify
    ])
    gen = AiLetterGen(caller, facts=FACTS)
    res = gen.generate([{"company_name": "ООО Тест", "mode": "NEWS",
                         "extra": {"news_object": "линия розлива",
                                   "city": "Балашиха"}}])
    assert res.rejected == {}
    assert 0 in res.ok and res.ok[0]["subject"] == "вопрос по воздуху"
    # раунды брака запротоколированы
    assert res.ok[0]["rounds"] and res.ok[0]["rounds"][0]["fails"]


def test_cycle_hopeless_letter_goes_to_rejects():
    """Провайдер упорно отдаёт брак — письмо в rejected, НЕ в ok."""
    bad = json.dumps({"letters": [BAD_LETTER]}, ensure_ascii=False)
    caller, _ = _fake_caller_factory([bad] * 20)
    gen = AiLetterGen(caller, facts=FACTS, rounds=2)
    res = gen.generate([{"company_name": "ООО Тест", "mode": "GENERIC"}])
    assert res.ok == {}
    assert 0 in res.rejected and res.rejected[0]


def test_verifier_rejection_triggers_fix():
    """Гейт чист, но верификатор бракует «рекламность» — уходит в fix."""
    caller, calls = _fake_caller_factory([
        json.dumps({"letters": [GOOD_LETTER]}, ensure_ascii=False),
        json.dumps({"verdicts": [{"idx": 0, "ok": False,
                                  "problems": ["реклама: витрина"]}]}),
        json.dumps({"letters": [GOOD_LETTER]}, ensure_ascii=False),   # fix
        json.dumps({"verdicts": [{"idx": 0, "ok": True}]}),
    ])
    gen = AiLetterGen(caller, facts=FACTS)
    res = gen.generate([{"company_name": "ООО Тест", "mode": "NEWS",
                         "extra": {"news_object": "линия розлива",
                                   "city": "Балашиха"}}])
    assert 0 in res.ok
    assert any("verify" in p.lower() or "vf" in p.lower() or "контролёр" in p
               for p in calls["prompts"][1:2])


def test_auto_mode_routing():
    """auto: есть news_object+city -> NEWS, иначе GENERIC (в промпте видно)."""
    caller, calls = _fake_caller_factory([
        json.dumps({"letters": [GOOD_LETTER]}, ensure_ascii=False),
        json.dumps({"verdicts": [{"idx": 0, "ok": True}]}),
    ])
    gen = AiLetterGen(caller, facts=FACTS)
    gen.generate([{"company_name": "ООО Тест", "mode": "auto",
                   "extra": {"news_object": "цех", "city": "Тверь"}}])
    assert "режим: NEWS" in calls["prompts"][0]


# ---- panel_settings + окно авто-отправки (owner: 9-11 пн-чт, настраиваемо) ----

def test_store_settings_roundtrip(tmp_path):
    from sender.store import Store
    st = Store(str(tmp_path / "s.db"))
    st.init_schema()
    assert st.get_setting("sending_window") is None
    win = {"days": [1, 2, 3, 4], "start": "09:00", "end": "11:00", "tz": "Europe/Moscow"}
    st.set_setting("sending_window", win)
    assert st.get_setting("sending_window") == win
    st.set_setting("sending_window", None)
    assert st.get_setting("sending_window") is None


def test_window_override_applies(tmp_path):
    """Override из panel_settings главнее конфига: пн-чт 09:00-11:00."""
    from datetime import datetime, timezone as _tz
    from sender.store import Store
    from sender.sender import Sender

    class _Cfg:
        def get(self, k, d=None):
            return {"timezone": "Europe/Moscow"}.get(k, d)
        def sending_window(self):
            raise AssertionError("конфиг не должен спрашиваться при override")
        def holidays(self):
            return set()

    st = Store(str(tmp_path / "w.db"))
    st.init_schema()
    st.set_setting("sending_window",
                   {"days": [1, 2, 3, 4], "start": "09:00", "end": "11:00",
                    "tz": "Europe/Moscow"})
    snd = Sender.__new__(Sender)   # без полного конструктора: только нужные поля
    snd.config = _Cfg()
    snd.store = st
    # четверг 10:00 МСК (=07:00 UTC) — внутри окна
    ok = snd._within_window(datetime(2026, 7, 23, 7, 0, tzinfo=_tz.utc))
    # пятница 10:00 МСК — день 5 не в списке
    fri = snd._within_window(datetime(2026, 7, 24, 7, 0, tzinfo=_tz.utc))
    # четверг 12:00 МСК — позже конца окна
    late = snd._within_window(datetime(2026, 7, 23, 9, 0, tzinfo=_tz.utc))
    assert ok is True and fri is False and late is False
