# -*- coding: utf-8 -*-
"""Вердикт пробы доезжает до базы обогащения.

Владелец 12.08: «а почты убираются в принципе из всех баз?». Ответ был «нет»:
мёртвый адрес ложился в стоп-лист панели (письмо не уйдёт), но в enrich.db
продолжал лежать как обычный контакт — и снова попадал в отбор кандидатов,
снова тратил генерацию, снова снимался на последнем рубеже. Так и вышло со
snab@volga-ice.ru: сервер сказал «нет такого ящика», а в обогащении у него
стояло mx_ok=1 и роль «снабжение/закупки».

Здесь проверяем ровно две вещи: вердикт записывается в свои колонки (чужие
mx_ok/addr_class не трогаем — их смысл заполняет обогащение), и отбор
кандидатов умеет по нему отсеивать заведомо недоставимых.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from sender import probe_enrich as PE  # noqa: E402
from sender.addr_probe import НЕТ_MX, НЕТ_ЯЩИКА, НЕЯСНО, ЕСТЬ  # noqa: E402


@pytest.fixture
def обогащение(tmp_path):
    путь = str(tmp_path / "enrich.db")
    con = sqlite3.connect(путь)
    con.execute("CREATE TABLE emails (email TEXT, source TEXT, mx_ok INTEGER, "
                "addr_class TEXT)")
    con.executemany("INSERT INTO emails (email, source, mx_ok, addr_class) "
                    "VALUES (?,?,?,?)",
                    [("snab@volga-ice.ru", "сайт", 1, "снабжение/закупки"),
                     ("info@zhivoy.ru", "сайт", 1, "общий"),
                     ("kto@nomx.ru", "чеко", 1, "общий")])
    con.commit()
    con.close()
    return путь


def _колонка(путь, адрес, имя):
    con = sqlite3.connect(путь)
    try:
        r = con.execute(f"SELECT {имя} FROM emails WHERE email=?",
                        (адрес,)).fetchone()
        return r[0] if r else None
    finally:
        con.close()


def test_verdikt_lozhitsya_v_obogashchenie(обогащение):
    итог = PE.записать(обогащение, [
        {"email": "snab@volga-ice.ru", "verdict": НЕТ_ЯЩИКА,
         "answer": "550 no such user"},
        {"email": "info@zhivoy.ru", "verdict": ЕСТЬ, "answer": "250 ok"}])
    assert итог["обновлено"] == 2 and итог["смертельных"] == 1
    assert _колонка(обогащение, "snab@volga-ice.ru", "probe_verdict") == НЕТ_ЯЩИКА
    assert "no such user" in _колонка(обогащение, "snab@volga-ice.ru",
                                      "probe_answer")
    assert _колонка(обогащение, "snab@volga-ice.ru", "probe_ts")


def test_chuzhie_kolonki_ne_zatirayutsya(обогащение):
    """mx_ok и роль заполняет обогащение своим смыслом — вердикт их не трогает:
    затерев, потеряем сведения о том, откуда взялся адрес."""
    PE.записать(обогащение, [{"email": "snab@volga-ice.ru",
                              "verdict": НЕТ_ЯЩИКА, "answer": "550"}])
    assert _колонка(обогащение, "snab@volga-ice.ru", "mx_ok") == 1
    assert _колонка(обогащение, "snab@volga-ice.ru",
                    "addr_class") == "снабжение/закупки"


def test_registr_adresa_ne_meshaet(обогащение):
    PE.записать(обогащение, [{"email": "Snab@Volga-Ice.RU", "verdict": НЕТ_MX}])
    assert _колонка(обогащение, "snab@volga-ice.ru", "probe_verdict") == НЕТ_MX


def test_net_bazy_ne_oshibka(tmp_path):
    """Панель обязана работать и без обогащения — тесты, чужая машина."""
    assert PE.записать(None, [{"email": "a@b.ru", "verdict": НЕТ_MX}])[
        "обновлено"] == 0
    assert PE.записать(str(tmp_path / "нет.db"),
                       [{"email": "a@b.ru", "verdict": НЕТ_MX}])["обновлено"] == 0


def test_otbor_vybrasyvaet_tolko_mertvyh(обогащение):
    PE.записать(обогащение, [
        {"email": "snab@volga-ice.ru", "verdict": НЕТ_ЯЩИКА},
        {"email": "kto@nomx.ru", "verdict": НЕТ_MX},
        {"email": "info@zhivoy.ru", "verdict": ЕСТЬ}])
    живые = PE.zhivye_tolko(обогащение, ["snab@volga-ice.ru", "kto@nomx.ru",
                                         "info@zhivoy.ru", "new@nikto.ru"])
    assert живые == {"info@zhivoy.ru", "new@nikto.ru"}


def test_neyasno_ne_prigovor(обогащение):
    """«Неясно» — это про сеть и серые списки, а не про адрес: такой контакт
    остаётся в работе, иначе выбросим живых по таймауту."""
    PE.записать(обогащение, [{"email": "info@zhivoy.ru", "verdict": НЕЯСНО}])
    assert "info@zhivoy.ru" in PE.zhivye_tolko(обогащение, ["info@zhivoy.ru"])


def test_bez_kolonki_otbor_ne_pusteet(обогащение):
    """Колонки ещё нет (вердиктов не записывали) — отбор возвращает всё, а не
    пустоту: отсутствие проверки не повод остаться без кандидатов."""
    сп = ["a@b.ru", "c@d.ru"]
    assert PE.zhivye_tolko(обогащение, сп) == set(сп)
    assert PE.zhivye_tolko(None, сп) == set(сп)


def test_naiti_bazu_ryadom_s_panelyu(tmp_path):
    class _Конфиг:
        def get(self, ключ, умолч=None):
            return умолч

    панель = tmp_path / "sender.db"
    панель.write_text("")
    assert PE.найти(_Конфиг(), str(панель)) is None      # enrich.db ещё нет
    (tmp_path / "enrich.db").write_text("")
    assert PE.найти(_Конфиг(), str(панель)) == str(tmp_path / "enrich.db")


def test_naiti_bazu_iz_nastroyki(tmp_path):
    class _Конфиг:
        def get(self, ключ, умолч=None):
            return r"D:\своя\enrich.db" if ключ == "service.enrich_db" else умолч

    assert PE.найти(_Конфиг(), str(tmp_path / "sender.db")) == r"D:\своя\enrich.db"


def test_tik_proby_donosit_verdikty(обогащение, monkeypatch):
    """Сквозная проверка: тик собственной пробы пишет вердикт в обогащение."""
    from sender.addr_probe import AddrProbe, AddrProbeLoop

    цикл = AddrProbeLoop.__new__(AddrProbeLoop)
    цикл.enrich_db = обогащение
    цикл.batch = 10
    цикл.last = {}
    цикл.enabled = lambda: True

    class _Хранилище:
        def confirm_list(self, **_k):
            return [{"id": 1, "email": "snab@volga-ice.ru", "kind": "outbound"}]

        def confirm_decide(self, *_a, **_k):
            return True

        def suppression_add(self, *_a, **_k):
            return None

    цикл.store = _Хранилище()
    проба = AddrProbe.__new__(AddrProbe)
    проба.new_pass = lambda: None
    проба.cached = lambda _a: None
    проба.probe = lambda a: {"email": a, "verdict": НЕТ_ЯЩИКА, "code": 550,
                             "answer": "no such user"}
    цикл.probe_ = проба
    monkeypatch.setattr("sender.lovushki.ЗаслонЛовушек",
                        lambda **_k: type("_", (), {
                            "применить": lambda self, п: {"снято": 0, "ид": []}})())

    итог = цикл.tick()
    assert итог["снято_писем"] == 1
    assert итог["в_обогащении"]["смертельных"] == 1
    assert _колонка(обогащение, "snab@volga-ice.ru", "probe_verdict") == НЕТ_ЯЩИКА
