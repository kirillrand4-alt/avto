"""Тесты направленческой генерации (задача 43): выбор направления, свои RULES
и факты Meyer, перекрёстная лексика в гейте, устойчивость без файла фактов.

Идут вместе с test_ai_letter.py (компрессорные тесты не трогаем: их прохождение
и есть доказательство, что КЦ-ветка не поехала)."""

import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.ai_letter import (  # noqa: E402
    AiLetterGen, MEYER_FACTS_PATH_DEFAULT, MEYER_GLOSSARY_PATH_DEFAULT,
    RULES_KC, RULES_MEYER, allowed_numbers, facts_block, gate, load_facts,
    log_results, norm_division, stamp_overflow, target_division,
    _equipment_hint,
)

MEYER_FACTS = {
    "division": "meyer",
    "total_crm": "больше 200 предприятий в России работают на оборудовании Meyer",
    "published_site": "",
    "region_counts_site_index": {},
    "clients_verified": {},
    "numbers_allowed": ["200"],
    "proof_points": ["офисы и демо-залы в Барнауле, Воронеже и Краснодаре"],
    "industries_typical": ["зерно, крупы, мукомольное производство"],
    "pains_typical": ["ручная переборка перестаёт справляться на объёме"],
}

KC_FACTS = {
    "total_crm": "больше 5580 внедрений по стране (CRM)",
    "published_site": "1018 опубликованных проектов на сайте",
    "region_counts_site_index": {"Барнаул": 78, "Москва": 69},
    "clients_verified": {},
}

MEYER_BODY = (
    "Добрый день!\n\n"
    "Попалась новость про цех переработки ягоды в Балашихе - на таком объеме "
    "ручная переборка обычно перестает справляться.\n\n"
    "Я веду направление Meyer, оптическая сортировка и рентген-инспекция.\n\n"
    "Подскажите, плодоножки и мусор после первичной очистки сейчас ловите "
    "руками, или всё решено - тогда и писать не стоит?\n\n"
    "С уважением,"
)

KC_BODY = (
    "Добрый день!\n\n"
    "Попалась новость про линию розлива в Балашихе - обычно под такие проекты "
    "воздух считают еще на этапе проектирования.\n\n"
    "Я подбираю компрессорное оборудование в Компрессор Центре, у нас 78 "
    "опубликованных кейсов по Барнаулу.\n\n"
    "Подскажите, компрессорную уже заложили в проект, или всё решено - тогда "
    "и писать не стоит?\n\n"
    "С уважением,"
)

NEWS_EXTRA = {"news_object": "цех переработки ягоды", "city": "Балашиха"}


# ------------------------------------------------------------ гейт Meyer -- #

def test_meyer_gate_clean_letter_passes():
    fails = gate("вопрос по сортировке", MEYER_BODY, mode="NEWS",
                 extra=NEWS_EXTRA, facts=MEYER_FACTS, division="meyer")
    assert fails == [], fails


def test_meyer_gate_catches_compressor_lexicon():
    """Главная боль задачи 43: Meyer-лиду ушло письмо про компрессоры и азот."""
    body = MEYER_BODY.replace(
        "Я веду направление Meyer, оптическая сортировка и рентген-инспекция.",
        "Я подбираю компрессоры и генераторы азота, считаю сжатый воздух.")
    fails = gate("вопрос по сортировке", body, mode="NEWS", extra=NEWS_EXTRA,
                 facts=MEYER_FACTS, division="meyer")
    names = " | ".join(fails)
    assert "компрессорная лексика" in names
    assert "азот" in names


def test_kc_gate_catches_meyer_lexicon():
    """Обратная сторона: компрессорному лиду нельзя писать про фотосепараторы."""
    fails = gate("вопрос по воздуху", MEYER_BODY, mode="NEWS", extra=NEWS_EXTRA,
                 facts=KC_FACTS, division="kc")
    names = " | ".join(fails)
    assert "meyer-лексика" in names


def test_meyer_numbers_are_own():
    """У Meyer свой канон числа: 200 можно, компрессорные 5580 - нет."""
    nums = allowed_numbers(MEYER_FACTS, None, "meyer")
    assert "200" in nums and "5580" not in nums
    body = MEYER_BODY.replace("Я веду направление Meyer",
                              "Я веду направление Meyer, больше 5580 внедрений")
    fails = gate("вопрос по сортировке", body, mode="NEWS", extra=NEWS_EXTRA,
                 facts=MEYER_FACTS, division="meyer")
    assert any("непроверенные числа" in f for f in fails)


def test_meyer_achievement_counted_once():
    body = MEYER_BODY.replace(
        "Я веду направление Meyer, оптическая сортировка и рентген-инспекция.",
        "Больше 200 предприятий уже работают на этом, больше 200 в России.")
    fails = gate("вопрос по сортировке", body, mode="NEWS", extra=NEWS_EXTRA,
                 facts=MEYER_FACTS, division="meyer")
    assert any("витрина" in f for f in fails)


def test_meyer_stamp_limits_are_own():
    """Свои анти-штампы: язык правил Meyer выгорает первым."""
    bodies = ["посторонние включения на линии"] * 3 + ["другое письмо"] * 2
    over = stamp_overflow(bodies, "meyer")
    assert any("включени" in o for o in over)
    # у КЦ такого счётчика нет - его штампы про другое
    assert stamp_overflow(bodies, "kc") == []


# ------------------------------------------------- выбор направления ------ #

def test_norm_division_composite_is_undecided():
    assert norm_division("meyer") == "meyer"
    assert norm_division("Компрессор Центр") == "kc"
    assert norm_division("kc+meyer") is None   # решает приоритет, не метка


def test_target_division_explicit_wins():
    rec = {"mode": "NEWS", "division": "meyer", "target_division": "kc",
           "extra": {"news_object": "линия фотосепарации", "city": "Тверь"}}
    assert target_division(rec) == ("kc", "explicit")


def test_target_division_by_news_beats_needs():
    """kc+meyer: повод про сортировку -> пишем про сортировку, хотя в
    потребностях есть и компрессоры."""
    rec = {"mode": "NEWS", "division": "kc+meyer",
           "extra": {"news_object": "линия фотосепарации зерна", "city": "Тверь",
                     "equipment": "Компрессоры, Фотосепараторы"}}
    div, why = target_division(rec)
    assert div == "meyer" and why == "news"


def test_target_division_news_over_needs_is_flagged():
    """Повод про одно, потребность про другое - направление берём по поводу,
    но помечаем, чтобы оператор увидел это в очереди."""
    rec = {"mode": "NEWS", "division": "kc+meyer",
           "extra": {"news_object": "новый компрессорный цех", "city": "Тверь",
                     "equipment": "Фотосепараторы"}}
    assert target_division(rec) == ("kc", "news_over_needs")


def test_target_division_by_needs():
    rec = {"mode": "GENERIC", "division": "kc+meyer",
           "extra": {"equipment": "Рентген-инспекция, фотосепараторы"}}
    assert target_division(rec) == ("meyer", "needs")


def test_target_division_by_base_label():
    rec = {"mode": "GENERIC", "division": "meyer", "extra": {}}
    assert target_division(rec) == ("meyer", "base_label")


def test_target_division_by_profile_okved():
    rec = {"mode": "GENERIC", "okved": "10.61", "activity": "производство круп",
           "extra": {}}
    assert target_division(rec) == ("meyer", "profile")


def test_target_division_fallback_is_kc():
    """Ничего не известно -> КЦ: 79% базы и единственные проверяемые счётчики."""
    rec = {"mode": "GENERIC", "company_name": "ООО Тест", "extra": {}}
    assert target_division(rec) == ("kc", "fallback")


def test_equipment_hint_drops_alien_products():
    assert _equipment_hint("Компрессоры, Фотосепараторы", "meyer") == "Фотосепараторы"
    assert _equipment_hint("Компрессоры, Фотосепараторы", "kc") == "Компрессоры"


# ------------------------------------------- факты и промпты Meyer -------- #

def test_facts_block_meyer_has_no_kc_content():
    block = facts_block(MEYER_FACTS, "meyer")
    assert "5580" not in block and "компрессор" not in block.lower()
    assert "200 предприятий" in block
    assert "ТИПИЧНЫЕ БОЛИ" in block


def test_pending_clients_never_reach_prompt():
    """clients_pending_owner - сырьё на вычитку владельцу, а не разрешение
    называть клиента в письме: в промпт он не попадает НИКОГДА."""
    facts = dict(MEYER_FACTS,
                 clients_pending_owner=[{"name": "ООО «Секретный Клиент»"}])
    assert "Секретный" not in facts_block(facts, "meyer")


def test_facts_block_kc_unchanged():
    block = facts_block(KC_FACTS, "kc")
    assert "5580" in block and "Барнаул" in block


def test_rules_are_different_sets():
    assert "5580" in RULES_KC and "5580" not in RULES_MEYER
    assert "Компрессор Центре" in RULES_KC and "Компрессор Центре" not in RULES_MEYER
    assert "фотосепаратор" in RULES_MEYER and "фотосепаратор" not in RULES_KC
    # компрессорные слова в правилах Meyer есть только как ЗАПРЕТ (правило 14)
    assert "ЗАПРЕЩЕНА" in RULES_MEYER.split("14. НАПРАВЛЕНИЕ")[1]
    # длинное тире встречается ровно один раз - в самом запрете (правило 4)
    assert RULES_MEYER.count("—") == 1
    assert 'БЕЗ длинных тире «—»' in RULES_MEYER


def test_load_facts_missing_meyer_file_fallback():
    """Файла фактов нет -> генератор не падает, просто пишет без цифр."""
    f = load_facts("/nonexistent/meyer-facts.json", division="meyer")
    assert f["total_crm"] == "" and f["region_counts_site_index"] == {}
    assert "проверяемых чисел нет" in facts_block(f, "meyer")


def test_shipped_meyer_files_parse():
    """На сервере (после деплоя) проверяем сами файлы; локально пропускаем."""
    if not os.path.exists(MEYER_FACTS_PATH_DEFAULT):
        pytest.skip("meyer-facts.json не развёрнут")
    facts = json.load(open(MEYER_FACTS_PATH_DEFAULT, encoding="utf-8"))
    for key in ("total_crm", "region_counts_site_index", "clients_verified",
                "industries_typical", "pains_typical"):
        assert key in facts
    if os.path.exists(MEYER_GLOSSARY_PATH_DEFAULT):
        gl = json.load(open(MEYER_GLOSSARY_PATH_DEFAULT, encoding="utf-8"))
        assert gl and all(isinstance(v, str) for v in gl.values())


# ----------------------------------------------------- цикл с фейком ------ #

def _smart_caller(bodies_by_division):
    """Фейковый провайдер: отдаёт письмо своего направления и всегда ок-вердикт.
    Пишет промпты в calls['prompts'] — по ним и проверяем, какие правила ушли."""
    calls = {"prompts": []}

    def caller(prompt):
        calls["prompts"].append(prompt)
        if '"verdicts"' in prompt:
            idxs = [int(x) for x in _find_all(prompt, "=== ПИСЬМО #")]
            return json.dumps({"verdicts": [{"idx": i, "ok": True} for i in idxs]})
        div = "meyer" if "направление Meyer" in prompt else "kc"
        idxs = [int(x) for x in _find_all(prompt, "=== ПОЛУЧАТЕЛЬ #")] or [0]
        return json.dumps({"letters": [
            {"idx": i, "subject": "вопрос по сортировке" if div == "meyer"
             else "вопрос по воздуху", "body": bodies_by_division[div]}
            for i in idxs]}, ensure_ascii=False)
    return caller, calls


def _find_all(text, marker):
    out, pos = [], text.find(marker)
    while pos >= 0:
        num = ""
        for ch in text[pos + len(marker):]:
            if ch.isdigit():
                num += ch
            else:
                break
        if num:
            out.append(num)
        pos = text.find(marker, pos + 1)
    return out


BODIES = {"kc": KC_BODY, "meyer": MEYER_BODY}


def test_generate_meyer_uses_meyer_rules_and_facts():
    caller, calls = _smart_caller(BODIES)
    gen = AiLetterGen(caller, facts_by_division={"meyer": MEYER_FACTS})
    res = gen.generate([{"company_name": "ООО Крупозавод", "mode": "NEWS",
                         "division": "meyer",
                         "extra": dict(NEWS_EXTRA,
                                       equipment="Компрессоры, Фотосепараторы")}])
    assert res.rejected == {}
    assert res.ok[0]["division"] == "meyer"
    gen_prompt_text = calls["prompts"][0]
    assert RULES_MEYER in gen_prompt_text and RULES_KC not in gen_prompt_text
    assert "5580" not in gen_prompt_text
    # подсказку по оборудованию почистили от чужих товаров
    assert "Компрессоры" not in gen_prompt_text.split("ПОЛУЧАТЕЛИ:")[-1]


def test_generate_kc_letter_has_no_meyer_lexicon():
    caller, calls = _smart_caller(BODIES)
    gen = AiLetterGen(caller, facts_by_division={"kc": KC_FACTS})
    res = gen.generate([{"company_name": "ООО Завод", "mode": "NEWS",
                         "division": "kc",
                         "extra": {"news_object": "линия розлива",
                                   "city": "Балашиха"}}])
    assert res.ok[0]["division"] == "kc"
    body = res.ok[0]["body"].lower()
    assert "фотосепаратор" not in body and "рентген" not in body
    assert "5580" in calls["prompts"][0]


def test_generate_mixed_batch_splits_prompts_by_division():
    """Смешанная партия: в одном промпте не должно быть двух наборов правил."""
    caller, calls = _smart_caller(BODIES)
    gen = AiLetterGen(caller, facts_by_division={"kc": KC_FACTS,
                                                 "meyer": MEYER_FACTS})
    res = gen.generate([
        {"company_name": "ООО Завод", "mode": "NEWS", "division": "kc",
         "extra": {"news_object": "линия розлива", "city": "Балашиха"}},
        {"company_name": "ООО Крупозавод", "mode": "NEWS", "division": "meyer",
         "extra": NEWS_EXTRA},
    ])
    assert res.rejected == {}
    assert res.ok[0]["division"] == "kc" and res.ok[1]["division"] == "meyer"
    gen_prompts = [p for p in calls["prompts"] if '"letters"' in p]
    assert len(gen_prompts) == 2
    for p in gen_prompts:
        assert (RULES_KC in p) != (RULES_MEYER in p)   # ровно один набор правил
    assert sum(RULES_MEYER in p for p in gen_prompts) == 1


def test_generate_without_facts_files_does_not_crash():
    """Ни одного файла фактов нет (боевой сервер до деплоя JSON) - письма
    всё равно генерируются, просто без цифр."""
    caller, _ = _smart_caller(BODIES)
    empty = load_facts("/nonexistent/meyer-facts.json", division="meyer")
    gen = AiLetterGen(caller, facts_by_division={"meyer": empty})
    res = gen.generate([{"company_name": "ООО Крупозавод", "mode": "NEWS",
                         "division": "meyer", "extra": NEWS_EXTRA}])
    assert 0 in res.ok and res.ok[0]["division"] == "meyer"


def test_log_results_adds_division_column(tmp_path):
    """Лог старой версии (без колонки division) обязан пережить апгрейд."""
    db = str(tmp_path / "sender.db")
    cx = sqlite3.connect(db)
    cx.execute("""CREATE TABLE ai_letter_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id INTEGER, recipient_id INTEGER,
        email TEXT, status TEXT, subject TEXT, body TEXT, rounds_json TEXT, created_at TEXT)""")
    cx.commit()
    cx.close()
    log_results(db, 7, [{"email": "a@b.ru", "recipient_id": 1, "status": "ok",
                         "subject": "s", "body": "b", "rounds": [],
                         "division": "meyer"}])
    log_results(db, 7, [{"email": "c@d.ru", "recipient_id": 2, "status": "brak",
                         "subject": "", "body": "", "rounds": [],
                         "division": "kc"}])
    cx = sqlite3.connect(db)
    rows = cx.execute("SELECT email, division FROM ai_letter_log ORDER BY id").fetchall()
    cx.close()
    assert rows == [("a@b.ru", "meyer"), ("c@d.ru", "kc")]
