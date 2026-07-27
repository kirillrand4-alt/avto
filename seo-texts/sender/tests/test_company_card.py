"""Тесты объединённой карточки (§1-2 ENGINEER-TASKS-BASE-MERGE).

Ключевые правила: направление ТОЛЬКО из базы обзвона; контакты enrich
приоритетнее; телефоны — оба набора с источником; site по verified;
cand_site с пометкой «не подтверждён»; деградация без индекса/enrich.
"""

import os
import sqlite3
import sys

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.company_card import (  # noqa: E402
    CompanyCards, DIVISION_BY_BASE, ObzvonIndex, build_company_card,
    build_obzvon_index, norm_inn,
)

_HEADER = (
    "База;ИНН;ОГРН;КПП;ОКПО;Краткое;Полное;Статус;ДатаРег;Адрес;Регион;ОПФ;"
    "УстКапитал;Директор;ИННдир;Учредители;ОсновнойОКВЭД;ВсеОКВЭД;Телефоны;"
    "Emails;Сайты;Телефоны с сайта;Email с сайта;ГодОтч;Выручка;ЧистПрибыль;"
    "Капитал;ССЧ;Итоговый балл приоритета;Макс. балл по связке;"
    "Оборудование по основному ОКВЭД;Все категории оборудования;"
    "Найденные ОКВЭД;Комментарий расчёта;Выручка, руб.;"
    "Приоритет × выручка / 10000")

_KC_ROW = (
    'Компрессор Центр;4201000625;1024200000000;420101001;12345678;'
    '"ООО ""Завод""";"ООО ""Кузбасский Завод""";Действующая компания;'
    '01 января 2000 года;650000, г. Кемерово, ул. Заводская, 1;Кемеровская область;'
    'ООО;10 000 руб.;Иванов Пётр Сидорович;420500000000;Иванов П.С.;'
    '25.11 Производство строительных металлических конструкций;'
    '25.11 Производство строительных металлических конструкций | '
    '28.13 Производство прочих насосов и компрессоров;'
    '+7 (384) 200-00-01 | +7 (384) 200-00-02;zavod@zavod.ru;zavod.ru;'
    '+7 (384) 200-00-03 доб. 12;sales@zavod.ru;2024;120 млн;10 млн;50 млн;35;'
    '16;10;Компрессоры поршневые;Компрессоры | Осушители;25.11, 28.13;'
    'связка ОКВЭД 28.13 даёт максимум;120000000;12')

_MEYER_ROW = (
    'Meyer;5404000000;1025400000000;540401001;87654321;"ООО ""Крупа""";'
    '"ООО ""Сибирская Крупа""";Действующая компания;05 мая 2010 года;'
    '630000, г. Новосибирск, ул. Мельничная, 5;Новосибирская область;ООО;'
    '20 000 руб.;Петров Иван Иванович;540600000000;Петров И.И.;'
    '10.61 Производство продуктов мукомольной промышленности;'
    '10.61 Производство продуктов мукомольной промышленности;'
    '+7 (383) 300-00-01;;krupa.ru;;;2024;300 млн;25 млн;90 млн;120;'
    '18;12;Фотосепараторы;Фотосепараторы | Рентген-инспекция;10.61;'
    'мукомолы — ядро Meyer;300000000;54')


def _build_index(tmp_path):
    db = str(tmp_path / "obzvon.db")
    stats = build_obzvon_index(
        iter([_HEADER, _KC_ROW, _MEYER_ROW, ";;;;bad-row-без-инн"]), db)
    return db, stats


def _make_enrich(tmp_path, **company_over):
    """enrich.db с расширенной схемой (cand_site, source_url — как на сервере)."""
    path = str(tmp_path / "enrich.db")
    if os.path.exists(path):
        os.unlink(path)
    cx = sqlite3.connect(path)
    cx.executescript(
        "CREATE TABLE companies(inn TEXT PRIMARY KEY, name TEXT, division TEXT,"
        " okved TEXT, region TEXT, pxr REAL, site TEXT, cand_site TEXT,"
        " activity TEXT, is_competitor INTEGER, verified TEXT, best_email TEXT,"
        " phones TEXT, updated_at TEXT);"
        "CREATE TABLE emails(inn TEXT, email TEXT, role TEXT, person TEXT,"
        " mx_ok INTEGER, source TEXT, source_url TEXT, updated_at TEXT);"
        "CREATE TABLE signals(inn TEXT, source TEXT, event_type TEXT, what TEXT,"
        " sum TEXT, source_url TEXT, hotness INTEGER, ts TEXT, updated_at TEXT);")
    comp = {"inn": "4201000625", "name": "ООО Завод", "division": "meyer",
            "okved": "25.11", "region": "Кемеровская область", "pxr": 12.0,
            "site": "zavod-new.ru", "cand_site": "", "activity": "металл",
            "is_competitor": 0, "verified": "inn",
            "best_email": "director@zavod-new.ru",
            "phones": "+7 (384) 200-11-11", "updated_at": "2026-07-20"}
    comp.update(company_over)
    cx.execute("INSERT INTO companies VALUES (%s)" % ",".join("?" * 14),
               list(comp.values()))
    cx.execute("INSERT INTO emails VALUES (?,?,?,?,?,?,?,?)",
               ("4201000625", "director@zavod-new.ru", "директор",
                "Иванов Пётр", 1, "site", "https://zavod-new.ru/contacts",
                "2026-07-20"))
    cx.execute("INSERT INTO signals VALUES (?,?,?,?,?,?,?,?,?)",
               ("4201000625", "news", "modernization",
                "Завод модернизирует цех", "120 млн",
                "https://news.ru/zavod-ceh", 8, "2026-07-15", "2026-07-20"))
    cx.commit()
    cx.close()
    return path


def test_index_builds_and_divisions(tmp_path):
    db, stats = _build_index(tmp_path)
    assert stats["rows"] == 2 and stats["skipped_no_inn"] == 1
    idx = ObzvonIndex(db)
    assert idx.available
    assert idx.division("4201000625") == "kc"
    assert idx.division("5404000000") == "meyer"
    assert idx.division("9999999999") is None  # не из базы = пусто
    row = idx.get("4201000625")
    # «ВсеОКВЭД» сжат до кодов, директор/выручка — из первоисточника
    assert row["okved_all_codes"] == "25.11|28.13"
    assert row["director"] == "Иванов Пётр Сидорович"
    assert row["priority_max"] == "10" and row["pxr"] == "12"


def test_equip_for_okved_canonical_format(tmp_path):
    """Единый формат потребности (владелец 27.07): для компании ВНЕ базы текст
    оборудования берётся из самой базы по основному ОКВЭД — точный код, затем
    обрезка сегментов; чужой код -> пусто."""
    db, _ = _build_index(tmp_path)
    idx = ObzvonIndex(db)
    # точный код из базы
    assert idx.equip_for_okved("25.11") == "Компрессоры поршневые"
    # длиннее, чем в базе: 25.11.1 -> обрезка до 25.11
    assert idx.equip_for_okved("25.11.1") == "Компрессоры поршневые"
    assert idx.equip_for_okved("10.61") == "Фотосепараторы"
    assert idx.equip_for_okved("64.19") == ""      # банков в базе нет
    assert idx.equip_for_okved("") == ""
    # фасад с кэшем отдаёт то же
    cards = CompanyCards(index_path=db)
    assert cards.equip_for_okved("25.11") == "Компрессоры поршневые"
    assert cards.equip_for_okved("25.11") == "Компрессоры поршневые"  # из кэша


def test_division_only_from_obzvon_enrich_is_guess(tmp_path):
    db, _ = _build_index(tmp_path)
    enrich = _make_enrich(tmp_path)  # enrich говорит meyer — база говорит kc
    card = build_company_card(
        "4201000625", obzvon=ObzvonIndex(db), enrich_db_path=enrich)
    assert card["division"] == "kc"            # базу не перебить
    assert card["division_guess"] == "meyer"   # только как предположение
    unknown = build_company_card(
        "7777777777", obzvon=ObzvonIndex(db), enrich_db_path=enrich)
    assert unknown["division"] is None         # не из базы = пусто


def test_contacts_enrich_first_phones_both_sets(tmp_path):
    db, _ = _build_index(tmp_path)
    enrich = _make_enrich(tmp_path)
    card = build_company_card(
        "4201000625", obzvon=ObzvonIndex(db), enrich_db_path=enrich)
    emails = card["contacts"]["emails"]
    assert emails[0]["origin"] == "enrich"     # enrich первым
    assert emails[0]["source_url"] == "https://zavod-new.ru/contacts"
    base_emails = {e["email"] for e in emails if e["origin"] == "obzvon"}
    assert {"zavod@zavod.ru", "sales@zavod.ru"} <= base_emails
    sources = {p["source"] for p in card["contacts"]["phones"]}
    assert {"база", "сайт, с доб.", "enrich"} <= sources  # оба набора + enrich


def test_site_verified_rule(tmp_path):
    db, _ = _build_index(tmp_path)
    ok = _make_enrich(tmp_path, verified="inn")
    card = build_company_card("4201000625", obzvon=ObzvonIndex(db),
                              enrich_db_path=ok)
    assert card["site_view"]["site"] == "zavod-new.ru"
    bad = _make_enrich(tmp_path, verified="guess")
    card = build_company_card("4201000625", obzvon=ObzvonIndex(db),
                              enrich_db_path=bad)
    assert card["site_view"]["site"] == ""     # непроверенный не показываем как site
    assert card["site_view"]["cand_site"] == "zavod-new.ru"
    assert card["site_view"]["cand_site_note"] == "не подтверждён"


def test_degraded_without_sources(tmp_path):
    card = build_company_card("4201000625", obzvon=ObzvonIndex(None),
                              enrich_db_path=str(tmp_path / "нет.db"))
    assert card["division"] is None and card["obzvon_available"] is False
    assert card["enrich"]["available"] is False
    facade = CompanyCards(index_path=None, enrich_db_path=None)
    assert facade.active is False              # гейт знает, что индекса нет
    assert facade.division("4201000625") is None


def test_cache_and_norm(tmp_path):
    db, _ = _build_index(tmp_path)
    cards = CompanyCards(index_path=db)
    assert cards.card("4201 000625") is cards.card("4201000625")  # кэш+канон
    assert norm_inn(" 4201-000625 ") == "4201000625"
    assert DIVISION_BY_BASE["meyer"] == "meyer"
