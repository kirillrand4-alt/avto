"""Заглушки из базы — заслон ловушек обязан их видеть.

19.08 письмо ушло на test@mail.ru (ООО «Дестрой») и отбилось. Адрес прошёл
всё: формат верный, MX у mail.ru есть, служебным «test» не считался,
доменной опечатки нет. Владелец спросил прямо: «у нас же есть фильтр спам
ловушек» — был, но такого класса в нём не было.

Проверяю обе стороны: заглушки ловятся, рабочие адреса не страдают.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender import lovushki as L  # noqa: E402


def test_test_mail_ru_lovitsya():
    вид = L.вид_ловушки("test@mail.ru")
    assert вид and вид[0] == L.ЗАГЛУШКА, вид


def test_prochie_zaglushki():
    for а in ("aaa@zavodatri.ru", "123@company.ru", "demo@zavod.ru",
              "qwerty@mail.ru", "example@firma.ru"):
        вид = L.вид_ловушки(а)
        assert вид and вид[0] == L.ЗАГЛУШКА, (а, вид)


def test_rabochie_adresa_ne_stradayut():
    """Дороже промаха только ложная тревога: выброшенный рабочий адрес мы
    не увидим никогда."""
    for а in ("mail@zavodsm18.ru", "info@firma.ru", "sales@zavod.ru",
              "testov@zavod.ru", "demo-centr@firma.ru", "aaa-stroy@mail.ru",
              "pto3@techno-modul.ru", "zakupki@zavod.ru"):
        assert L.вид_ловушки(а) is None, а


def test_sluzhebnye_po_prezhnemu_lovyatsya():
    вид = L.вид_ловушки("postmaster@firma.ru")
    assert вид and вид[0] == L.СЛУЖЕБНЫЙ
