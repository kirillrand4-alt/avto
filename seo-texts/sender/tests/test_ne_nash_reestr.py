"""Реестр «не наш адресат»: компания выпадает один раз и навсегда.

Повод — ООО «ВОЗДУХ» 20.08: снято вручную утром («сами производят
технические газы»), вернулось пересудом гейта, сгенерировалось снова.
Три письма по $0.6 за день на компанию, которой мы решили не писать.

Снятая карточка убирает ПИСЬМО, но не КОМПАНИЮ — пул кандидатов её не
помнит. Реестр помнит.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..")))

from sender.ne_nash import НеНаш  # noqa: E402

ВОЗДУХ = "5031023670"
ПРИЧИНА = "сами производят технические газы — не наш покупатель"


def _реестр(tmp_path, с_зеркалом=True):
    зерк = str(tmp_path / "enrich.db") if с_зеркалом else None
    return НеНаш(str(tmp_path / "sender.db"), зерк)


def test_zapisannaya_kompaniya_naydena(tmp_path):
    р = _реестр(tmp_path)
    assert р.есть(ВОЗДУХ) is False
    р.записать(ВОЗДУХ, ПРИЧИНА, "владелец")
    assert р.есть(ВОЗДУХ) is True
    assert ПРИЧИНА in р.причина(ВОЗДУХ)


def test_inn_normalizuetsya(tmp_path):
    """ИНН приходит и строкой с пробелами, и числом — это один ИНН."""
    р = _реестр(tmp_path)
    р.записать(" 5031023670 ", ПРИЧИНА, "владелец")
    assert р.есть(5031023670) is True
    assert р.есть("5031-023-670") is True


def test_povtor_ne_plodit_strok(tmp_path):
    р = _реестр(tmp_path)
    р.записать(ВОЗДУХ, ПРИЧИНА, "владелец")
    р.записать(ВОЗДУХ, "другая причина", "оператор")
    with sqlite3.connect(str(tmp_path / "sender.db")) as c:
        n = c.execute("SELECT COUNT(*) FROM ne_nash_adresat").fetchone()[0]
    assert n == 1
    assert р.причина(ВОЗДУХ) == "другая причина"


def test_nabor_optom(tmp_path):
    """Отбор кандидатов спрашивает партией, а не по одному."""
    р = _реестр(tmp_path)
    for i in ("7701234567", "7702345678"):
        р.записать(i, ПРИЧИНА, "владелец")
    вышло = р.набор(["7701234567", "7702345678", "7703456789"])
    assert вышло == {"7701234567", "7702345678"}


def test_zerkalo_v_obogashchenie(tmp_path):
    """Вторая база нужна отбору кандидатов — он живёт отдельно от панели."""
    р = _реестр(tmp_path)
    р.записать(ВОЗДУХ, ПРИЧИНА, "владелец")
    with sqlite3.connect(str(tmp_path / "enrich.db")) as c:
        r = c.execute("SELECT prichina FROM ne_nash_adresat WHERE inn=?",
                      (ВОЗДУХ,)).fetchone()
    assert r and ПРИЧИНА in r[0]


def test_sboy_zerkala_ne_otmenyaet_reshenie(tmp_path):
    """Недоступность второй базы не должна ронять решение оператора."""
    р = НеНаш(str(tmp_path / "sender.db"), str(tmp_path / "нет" / "e.db"))
    assert р.записать(ВОЗДУХ, ПРИЧИНА, "владелец") is True
    assert р.есть(ВОЗДУХ) is True


def test_mozhno_vernut(tmp_path):
    """Решение человека бывает ошибочным — возврат обязан работать."""
    р = _реестр(tmp_path)
    р.записать(ВОЗДУХ, ПРИЧИНА, "владелец")
    р.убрать(ВОЗДУХ)
    assert р.есть(ВОЗДУХ) is False
    with sqlite3.connect(str(tmp_path / "enrich.db")) as c:
        assert c.execute("SELECT COUNT(*) FROM ne_nash_adresat "
                         "WHERE inn=?", (ВОЗДУХ,)).fetchone()[0] == 0


def test_pustoy_inn_ne_pishetsya(tmp_path):
    р = _реестр(tmp_path)
    assert р.записать("", ПРИЧИНА, "владелец") is False
    assert р.набор([""]) == set()
