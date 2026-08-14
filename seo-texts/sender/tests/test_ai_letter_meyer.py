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
    # Правка редактора 14.08: про ручную переборку не пишем (на элеваторах и
    # зерноперерабатывающих её нет), довод строим на требуемом качестве.
    "pains_typical": ["на объёме трудно держать стабильное качество партии"],
}

KC_FACTS = {
    "total_crm": "больше 5580 внедрений по стране (CRM)",
    "published_site": "1018 опубликованных проектов на сайте",
    "region_counts_site_index": {"Барнаул": 78, "Москва": 69},
    "clients_verified": {},
}

MEYER_BODY = (
    "Добрый день!\n\n"
    "Попалась новость про цех переработки ягоды у «Крупозавода» в Балашихе - "
    "на таком объеме продукцию обычно доводят до требуемого качества уже "
    "автоматической сортировкой.\n\n"
    "Я веду направление Meyer, оптическая сортировка и рентген-инспекция.\n\n"
    "Подскажите, плодоножки и мусор после первичной очистки сейчас ловите "
    "руками, или всё решено - тогда и писать не стоит?\n\n"
    "С уважением,"
)

KC_BODY = (
    "Добрый день!\n\n"
    "Попалась новость про линию розлива «Завода» в Балашихе - обычно под "
    "такие проекты воздух считают еще на этапе проектирования.\n\n"
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


def test_tehlinza_meyer_ne_trebuet_szhatogo_vozduha():
    """Техлинза компрессорного направления бракует ВСЕ письма Meyer.

    Замер на живом прогоне 12.08: из очереди «мейер-рентген» не вышло ни одного
    письма, причина у всех одна — «письмо о рентген-инспекции включений, не о
    компрессорном оборудовании, нет утверждения про сжатый воздух/азот/
    кислород». Оба промпта линзы написаны под компрессоры и требуют связки,
    которой у Meyer быть не может. Каждая такая попытка стоила 7,5 минут.
    """
    from sender.ai_letter import teh_lens_prompt

    items = [(0, "ООО Мельница", "мукомольное производство", "10.61",
              "Тема", "Тело письма")]
    for линза in ("технолог", "скептик"):
        kc = teh_lens_prompt(items, линза, "kc")
        assert ("сжатый воздух" in kc
                or "воздуха/азота/кислорода" in kc), линза
        for div in ("meyer", "meyer_foto", "meyer_rentgen"):
            m = teh_lens_prompt(items, линза, div)
            assert "фотосепаратор" in m or "оптическая сортировка" in m, (линза, div)
            assert "рентген" in m, (линза, div)
            # Главное: отсутствие сжатого воздуха не должно быть претензией.
            assert ("НЕ идёт и идти не должно" in m
                    or "претензией НЕ является" in m), (линза, div)


def test_tehlinza_delit_partiyu_po_napravleniyu():
    """В одной партии могут ехать письма обоих направлений — линза не должна
    судить их одним промптом."""
    import sender.ai_letter as AL

    спрошено = []

    class Ген(AL.AiLetterGen):
        def _ask(self, prompt, tag):
            спрошено.append((tag, prompt))
            return {"verdicts": []}

    g = Ген(lambda p: "", facts={}, default_division="kc")
    letters = {0: {"subject": "a", "body": "b"}, 1: {"subject": "c", "body": "d"}}
    recipients = {0: {"company_name": "Завод", "activity": "", "okved": "25.62"},
                  1: {"company_name": "Мельница", "activity": "", "okved": "10.61"}}
    g._teh_lens_verdicts([0, 1], letters, recipients,
                         {0: "kc", 1: "meyer_rentgen"})
    # Делим по маркеру Meyer: мейеровский промпт тоже упоминает сжатый
    # воздух — ровно затем, чтобы сказать «его отсутствие не претензия».
    мейеровских = [p for _, p in спрошено if "фотосепаратор" in p]
    компрессорных = [p for _, p in спрошено if "фотосепаратор" not in p]
    assert компрессорных, "письмо КЦ должно судиться компрессорной линзой"
    assert мейеровских, "письмо Meyer должно судиться своей линзой"
    # И письма не должны перемешаться в одном промпте.
    assert all("Мельница" not in p for p in компрессорных)
    assert all("Завод" not in p for p in мейеровских)


def test_gate_lovit_pryamuyu_ssylku_na_novost_v_generic():
    """«Прочитал новость о…» в GENERIC — выдумка: повода письму не давали.

    Поймано владельцем 12.08 в живой очереди: письмо омскому свинокомплексу
    начиналось «Прочитал новость о расширении производства комбикормов», хотя
    новости такой не было — модель пересказала профиль компании из карточки.
    Прежний заслон ждал «вижу/заметил» и эту форму пропускал.
    """
    from sender.ai_letter import gate

    тело = ("Добрый день!\n\nПрочитал новость о расширении производства "
            "комбикормов и переработки свинины в ООО «ТИТАН - АГРО». На таких "
            "объёмах металлодетектор стоит почти у всех.\n\nС уважением,")
    fails = gate("Вопрос по контролю включений", тело, mode="GENERIC",
                 division="meyer")
    assert any("псевдо-новость" in str(f) for f in fails), fails

    # В NEWS-режиме та же фраза законна: повод там реальный и лежит в extra.
    fails_news = gate("Вопрос по контролю включений", тело, mode="NEWS",
                      division="meyer")
    assert not any("псевдо-новость" in str(f) for f in fails_news), fails_news


def test_digest_ne_beryot_novost_pro_druguyu_kompaniyu(tmp_path):
    """Новость должна упоминать компанию, иначе это чужое событие по ИНН.

    Омскому «ТИТАН-АГРО» (свинина, комбикорма) матчинг приклеил новость про
    завод полиформальдегида на Кирово-Чепецком химкомбинате. Панель это видела
    и показывала оператору «НЕТ имени — проверь», а генерация ту же сверку не
    делала и строила на этом письмо.
    """
    import sqlite3

    from sender.ai_quota import AiQuota

    п = tmp_path / "enrich.db"
    con = sqlite3.connect(str(п))
    con.execute("CREATE TABLE signals (inn TEXT, event_type TEXT, what TEXT, "
                "sum TEXT, source_url TEXT, hotness INT, suspect INT)")
    con.execute("INSERT INTO signals VALUES (?,?,?,?,?,?,?)", (
        "5501092795", "новый завод",
        "На Кирово-Чепецком химическом комбинате строится завод полиформальдегида",
        "13,6 млрд рублей", "https://polymery.ru/x", 4, 0))
    con.commit()
    con.close()

    q = AiQuota.__new__(AiQuota)
    q._enrich_db = str(п)

    # Имя компании в тексте новости не встречается — повода нет.
    assert q._digest("5501092795", 'ООО "ТИТАН - АГРО"') == {}
    # Сверить нечем (имя не передали) — прежнее поведение, повод отдаём.
    assert q._digest("5501092795")["news_type"] == "новый завод"
    # Имя есть в тексте — повод законный.
    assert q._digest("5501092795", "Кирово-Чепецкий химкомбинат")["news_type"] \
        == "новый завод"


def test_rentgen_ne_vidit_kost_volos_derevo_perchatki():
    """Правка владельца 12.08: рентген видит плотное, а не всё подряд.

    Кость, волос, дерево и обрывки перчаток близки продукту по плотности —
    детектор их не находит. Модель называла их находкой рентгена уверенно и
    складно, а специалист по пищевой безопасности видит такую ошибку на первой
    строке. Разрешённый перечень: стекло, керамика, металл, силикон, камень.
    """
    from sender.ai_letter import gate

    основа = ("Добрый день!\n\nЯ веду направление Meyer, рентген-инспекция "
              "инородных включений. Детектор просвечивает упаковку и находит "
              "{}.\n\nПодскажите, актуально ли.\n\nС уважением,")
    for плохое, метка in (("волос и нитки", "волос"),
                          ("щепки дерева", "дерево"),
                          ("обрывки перчаток", "перчат")):
        fails = gate("Вопрос по контролю включений", основа.format(плохое),
                     mode="GENERIC", division="meyer")
        assert any("рентген не видит" in str(f) for f in fails), (плохое, fails)

    # Кость слово не запрещённое: толстая кость видна, дело в плотности
    # продукта и размере включения (уточнение владельца 12.08). Запрещено её
    # ОБЕЩАТЬ, а это ловит инженерная линза, а не механический заслон.
    kost = gate("Вопрос по контролю включений", основа.format("осколки кости"),
                mode="GENERIC", division="meyer")
    assert not any("рентген не видит" in str(f) for f in kost), kost

    # Разрешённый перечень проходит.
    ok = gate("Вопрос по контролю включений",
              основа.format("стекло, керамику, металл и силикон"),
              mode="GENERIC", division="meyer")
    assert not any("рентген не видит" in str(f) for f in ok), ok


def test_fotoseparatoru_derevo_razresheno():
    """У сортировки щепка в зерновом потоке — законная задача, не ошибка."""
    from sender.ai_letter import gate

    тело = ("Добрый день!\n\nЯ веду направление Meyer, оптическая сортировка. "
            "Сепаратор убирает из потока щепки дерева и камень перед "
            "помолом.\n\nПодскажите, актуально ли.\n\nС уважением,")
    fails = gate("Вопрос по сортировке зерна", тело, mode="GENERIC",
                 division="meyer")
    assert not any("рентген не видит" in str(f) for f in fails), fails


def test_generic_pismo_poluchaet_svoyu_mehaniku_zahoda():
    """У холодного письма механики захода не было — отсюда «смотрел профиль» везде.

    Замер очереди 12.08 (владелец: «режет глаз, везде повторяется»): 80% писем
    группы фото и 60% металлообработки начинались одинаково. У новостного
    режима механика назначалась ротацией с самого начала, у холодного — нет.
    """
    import sender.ai_letter as AL

    рек = {"company_name": "ООО Завод", "okved": "25.62", "extra": {}}
    блоки = [AL._recipient_block(i, рек, "kc", 0) for i in range(8)]
    for б in блоки:
        assert "МЕХАНИКА ЗАХОДА" in б, б
        # Заранее заход НЕ запрещаем (владелец 12.08 отменил запрет в пользу
        # квоты): промпт говорит про первую фразу только тому письму, которому
        # квота партии велела её сменить.
        assert "ПЕРВАЯ ФРАЗА" not in б, б
    с_пометкой = AL._recipient_block(
        0, dict(рек, extra={"сменить_заход": "от профиля"}), "kc", 0)
    assert "ПЕРВАЯ ФРАЗА" in с_пометкой and "от профиля" in с_пометкой
    # Соседние письма получают РАЗНЫЕ механики, а не одну на всех.
    механики = {б.split("МЕХАНИКА ЗАХОДА для этого письма (только она):")[1]
                .split("\n")[0].strip() for б in блоки}
    assert len(механики) >= 6, механики

    # У Meyer свой набор — про сортировку и контроль, а не про сжатый воздух.
    мблок = AL._recipient_block(0, dict(рек, okved="10.61"), "meyer", 0)
    # У Meyer ярлык другой: первая строка занята представлением по канону
    # редактора, поэтому механика управляет абзацем о получателе.
    мех = мблок.split("УГОЛ РАЗГОВОРА для этого письма (только он):")[1]
    assert "воздух" not in мех.lower()


def test_antishtamp_lovit_realnuyu_formulirovku():
    """Лимит стоял на «смотрел ваш», а модель писала «смотрел профиль» — мимо."""
    from sender.ai_letter import stamp_overflow

    письма = [f"Смотрел профиль компании №{i}. Вопрос по оборудованию."
              for i in range(6)]
    израсходовано = stamp_overflow(письма, "kc")
    assert израсходовано, "шесть одинаковых заходов обязаны сработать лимитом"


def test_mehaniki_zahoda_ne_soderzhat_stop_slov():
    """Система не должна диктовать оборот, за который сама же бракует.

    Замер 12.08: 18 браков из 30 по всем кампаниям дал один оборот
    «закладывают» — и он стоял в двух НАШИХ ЖЕ механиках захода Meyer, при
    том что гейт бракует любое «закладыва». Модель послушно писала
    продиктованное и вылетала. Тот же класс ошибки — длинное тире и слово
    «цена» в подсказке.
    """
    import re

    import sender.ai_letter as AL

    пулы = (AL.NEWS_MECHANICS, AL.NEWS_MECHANICS_MEYER,
            AL.GENERIC_MECHANICS, AL.GENERIC_MECHANICS_MEYER)
    нарушения = []
    for rx, имя in AL.STOP_RE:
        # Плейсхолдер {news_object} в NEWS-механиках законен: он
        # подставляется до попадания в письмо.
        if "плейсхолдер" in имя:
            continue
        for пул in пулы:
            for м in пул:
                if re.search(rx, м):
                    нарушения.append((имя, м[:70]))
    assert not нарушения, нарушения


def test_zahod_sam_po_sebe_ne_brak():
    """Запрет одного захода отменён — брак наступает только по квоте партии.

    12.08 запрет «не начинай со Смотрел профиль» стоял и в промпте, и в гейте.
    Разбор 118 ОТПРАВЛЕННЫХ писем показал, что этот заход в них основной, а
    вывод «раз на них отвечают, значит он работает» неверен: заход был почти во
    всех письмах, сравнивать не с чем. Зато видно другое — жёсткий запрет
    проблему не решил, а подвинул: 37% партии начались с «На».

    Владелец: «заменить запрет на квоту». Форму зачина ограничивает
    zahod_overflow по партии (см. test_zahod_kvota.py), а гейт следит лишь за
    тем, чтобы помеченное письмо не повторило свою форму.
    """
    from sender.ai_letter import gate

    письмо = ("Добрый день!\n\nСмотрел профиль «Гладиум»: металлические двери, "
              "значит есть пескоструй.\n\nПодскажите, актуально ли.\n\n"
              "С уважением,")
    fails = gate("Вопрос по оборудованию", письмо, mode="GENERIC", division="kc")
    assert not any("заход" in str(f) for f in fails), fails

    помечено = gate("Вопрос по оборудованию", письмо, mode="GENERIC",
                    division="kc", extra={"сменить_заход": "от профиля"})
    assert any("заход" in str(f) for f in помечено), помечено

    # Тот же оборот НЕ в первой фразе — законен даже у помеченного письма.
    норм = ("Добрый день!\n\nГде у вас на участке критичен сжатый воздух? "
            "Смотрел профиль компании, чтобы понять специфику.\n\n"
            "С уважением,")
    ok = gate("Вопрос по оборудованию", норм, mode="GENERIC", division="kc",
              extra={"сменить_заход": "от профиля"})
    assert not any("заход" in str(f) for f in ok), ok


def test_kost_ne_upominaem_vovse():
    """Правка редактора 12.08: любое упоминание кости требует оговорки про
    размер и плотность, а в первом письме она лишняя. Включая косточки ягод."""
    from sender.ai_letter import gate

    основа = ("Добрый день!\n\nГде у вас на линии стоит контроль продукта? "
              "Рентген-детектор находит {}.\n\nС уважением,")
    for плохое in ("осколки кости", "косточки ягод", "костные включения",
                   "кость в фарше"):
        fails = gate("Вопрос по контролю включений", основа.format(плохое),
                     mode="GENERIC", division="meyer")
        assert any("кость не упоминаем" in str(f) for f in fails), плохое

    ok = gate("Вопрос по контролю включений",
              основа.format("стекло, керамику, металл и силикон"),
              mode="GENERIC", division="meyer")
    assert not any("кость не упоминаем" in str(f) for f in ok), ok


def test_sdvig_mehaniki_razvodit_peregeneraciyu():
    """Перегенерация идёт по одному письму: без сдвига все получают первую
    механику, и штамп меняется на другой штамп."""
    import sender.ai_letter as AL

    рек = {"company_name": "ООО Завод", "okved": "25.62", "extra": {}}
    базовая = AL._recipient_block(0, рек, "kc", 0)
    механики = set()
    for сдвиг in range(len(AL.GENERIC_MECHANICS)):
        б = AL._recipient_block(0, dict(рек, extra={"angle_shift": сдвиг}),
                                "kc", 0)
        механики.add(б.split("(только она):")[1].split("\n")[0].strip())
    assert len(механики) == len(AL.GENERIC_MECHANICS), механики
    # Без сдвига поведение прежнее.
    assert базовая == AL._recipient_block(0, dict(рек, extra={}), "kc", 0)


def test_mehaniki_zadayut_raznuyu_formu_pervoy_frazy():
    """Разного содержания мало — нужен разный ЗАЧИН.

    Замер 12.08 после первой сотни перегенераций: штамп «Смотрел профиль»
    ушёл, но 37% писем начались со слова «На» («На производствах X сжатый
    воздух...»), а «на производствах металлоконструкций» повторилось дословно
    трижды. Причина: все механики просили назвать участок — то есть сами
    задавали один и тот же зачин. Теперь каждая механика диктует СВОЮ форму
    первой фразы.
    """
    import re

    import sender.ai_letter as AL

    for пул, имя in ((AL.GENERIC_MECHANICS, "kc"),
                     (AL.GENERIC_MECHANICS_MEYER, "meyer")):
        # У каждой механики есть указание на форму зачина: либо явное слово
        # для начала, либо требование начать с вопроса.
        без_формы = [м for м in пул
                     if not re.search(r'(?i)(начни|первое слово|первой строкой|'
                                      r'первая фраза)', м)]
        assert not без_формы, (имя, без_формы)
        # Диктуемые первые слова не должны совпадать у разных механик —
        # иначе разброс мнимый.
        зачины = re.findall(r'"([^"]{2,20})"', " ".join(пул))
        assert len(зачины) >= 8, (имя, зачины)
        assert len(set(з.lower() for з in зачины)) >= 8, (имя, зачины)


def test_linzy_idey_po_napravleniyu():
    """Идея захода не должна звать кофейное производство к сжатому воздуху.

    Замер 14.08: карточки #1049 и #1054 (кофе, направление Meyer) получили
    идеи «модульная система сжатого воздуха» и «аудит пневматических систем»,
    потому что все три линзы были написаны про компрессоры. Идея едет в промпт
    как опора, и модель за неё тянется — значит линзы обязаны знать станок.
    """
    from sender.ai_quota import AiQuota
    кц = AiQuota._IDEA_LENSES_KC
    meyer = AiQuota._IDEA_LENSES_MEYER
    assert any("компрессорн" in t for t in кц.values())
    assert not any("компрессорн" in t or "сжат" in t for t in meyer.values())
    assert any("рентген" in t for t in meyer.values())
    assert any("сортировк" in t for t in meyer.values())
