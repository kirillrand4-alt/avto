"""Приговор «мёртв» доезжает до стоп-листа и до обогащения, несмотря на замок.

26.08: 5120 приговоров «нет ящика»/«нет MX» не попали в стоп-лист, а 5024 —
в обогащение. Обе записи ломались об одно и то же: чужой поток держал базу,
первый же сбой проглатывался, и вся пачка молча возвращалась нулями.
"""

import os
import sqlite3
import sys

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender import probe_enrich  # noqa: E402


class Капризное:
    """Обёртка над соединением: роняет заданные UPDATE, остальное пропускает.

    Подменять sqlite3.Connection.execute нельзя - тип неизменяемый, поэтому
    подсовываем обёртку вместо самого соединения.
    """

    def __init__(self, con, ронять, сколько=99):
        self._con = con
        self._ронять = ронять
        self._осталось = сколько
        self.сорвано = 0

    def execute(self, sql, *арг, **кв):
        if (sql.startswith("UPDATE emails") and self._осталось
                and self._ронять(арг)):
            self._осталось -= 1
            self.сорвано += 1
            raise sqlite3.OperationalError("database is locked")
        return self._con.execute(sql, *арг, **кв)

    def __getattr__(self, имя):
        return getattr(self._con, имя)


def _база(путь):
    con = sqlite3.connect(путь)
    con.execute("CREATE TABLE emails (inn TEXT, email TEXT)")
    con.executemany("INSERT INTO emails (inn, email) VALUES (?,?)",
                    [("1", "a@x.ru"), ("2", "B@X.RU"), ("3", "c@y.ru")])
    con.commit()
    con.close()
    return путь


def test_verdikt_lozhitsya_po_lyubomu_registru(tmp_path):
    п = _база(str(tmp_path / "enrich.db"))
    итог = probe_enrich.записать(п, [
        {"email": "a@x.ru", "verdict": "нет ящика", "answer": "нет такого"},
        {"email": "b@x.ru", "verdict": "нет MX", "answer": ""},
    ])
    assert итог["обновлено"] == 2
    assert итог["смертельных"] == 2
    con = sqlite3.connect(п)
    строки = dict(con.execute(
        "SELECT lower(email), probe_verdict FROM emails").fetchall())
    con.close()
    assert строки["a@x.ru"] == "нет ящика"
    assert строки["b@x.ru"] == "нет MX"
    assert строки["c@y.ru"] is None


def test_odna_zapertaya_stroka_ne_horonit_pachku(tmp_path, monkeypatch):
    """Сбой на одной строке считается и не отменяет остальные."""
    п = _база(str(tmp_path / "enrich.db"))
    держим = []
    # Настоящий connect берём ДО подмены: probe_enrich.sqlite3 — тот же
    # объект модуля, и вызов внутри подмены ушёл бы в неё же.
    настоящий = sqlite3.connect

    def подмена(путь, **кв):
        об = Капризное(настоящий(путь, **кв),
                       lambda арг: bool(арг) and арг[0][3] == "a@x.ru")
        держим.append(об)
        return об

    monkeypatch.setattr(probe_enrich.sqlite3, "connect", подмена)
    monkeypatch.setattr(probe_enrich.time, "sleep", lambda _с: None)
    итог = probe_enrich.записать(п, [
        {"email": "a@x.ru", "verdict": "нет ящика", "answer": ""},
        {"email": "c@y.ru", "verdict": "нет MX", "answer": ""},
    ])
    monkeypatch.undo()
    assert держим[0].сорвано == 3, "упорную строку пробуем трижды"
    assert итог["не_легло"] == 1
    assert итог["обновлено"] == 1, "вторая строка обязана лечь"
    con = sqlite3.connect(п)
    assert con.execute("SELECT probe_verdict FROM emails WHERE email='c@y.ru'"
                       ).fetchone()[0] == "нет MX"
    con.close()


def test_zamok_perezhidaetsya_i_stroka_lozhitsya(tmp_path, monkeypatch):
    """Замок отпустили со второй попытки — вердикт всё равно записан."""
    п = _база(str(tmp_path / "enrich.db"))
    настоящий = sqlite3.connect

    def подмена(путь, **кв):
        return Капризное(настоящий(путь, **кв), lambda арг: True, сколько=1)

    monkeypatch.setattr(probe_enrich.sqlite3, "connect", подмена)
    monkeypatch.setattr(probe_enrich.time, "sleep", lambda _с: None)
    итог = probe_enrich.записать(
        п, [{"email": "a@x.ru", "verdict": "нет ящика", "answer": ""}])
    monkeypatch.undo()
    assert итог["обновлено"] == 1
    assert "не_легло" not in итог


def test_pustaya_stroka_schitaetsya_propuskom(tmp_path):
    п = _база(str(tmp_path / "enrich.db"))
    итог = probe_enrich.записать(п, [{"email": "", "verdict": "нет ящика"},
                                     {"email": "a@x.ru", "verdict": ""}])
    # Строку без адреса отбрасывает предварительный фильтр, до счётчика она
    # не доходит; в «пропущено» попадает только пустой вердикт.
    assert итог["пропущено"] == 1
    assert итог["обновлено"] == 0
