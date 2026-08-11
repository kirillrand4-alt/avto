# -*- coding: utf-8 -*-
"""Боли: две градации Meyer и поиск по дополнительным ОКВЭДам.

Оба правила пришли от владельца 11.08 и оба чинят конкретный вред:
  * одна общая боль на Meyer писала мукомолу про пневмотранспорт (железо КЦ)
    вместо сортировки зерна;
  * боль искалась только по ОСНОВНОМУ коду, хотя в отбор компания попадает по
    любому своему — завод с основным «розлив воды» и дополнительным
    «мукомольное» получал письмо про воду.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import sender.ai_letter as AL  # noqa: E402

ПАМЯТКА = {
    "kc": {"25": "сжатый воздух в цехе", "10.61": "пневмотранспорт муки"},
    "meyer": {"10": "общая боль пищёвки"},
    "meyer_foto": {"10.61": "сортировка зерна по цвету и дефекту перед помолом"},
    "meyer_rentgen": {"10.13": "плотные включения в фарше"},
    "_meyer_gradaciya": {"10.61": "фото", "10.13": "рентген"},
    "_по_умолчанию": {"kc": "сжатый воздух", "meyer": "контроль продукта"},
}


@pytest.fixture(autouse=True)
def _подменить_боли(tmp_path, monkeypatch):
    п = tmp_path / "pains.json"
    п.write_text(json.dumps(ПАМЯТКА, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(AL, "OKVED_PAINS_PATH", str(п))
    monkeypatch.setattr(AL, "_OKVED_PAINS", None)
    yield
    AL._OKVED_PAINS = None


def test_meyer_vybiraet_gradaciyu_po_kodu():
    """Мукомолу — сортировка, мясопереработке — рентген. Не наоборот."""
    assert "сортировка зерна" in AL.equipment_pitch("10.61", "meyer")
    assert "включения в фарше" in AL.equipment_pitch("10.13", "meyer")


def test_gradaciyu_mozhno_nazvat_pryamo():
    assert "сортировка зерна" in AL.equipment_pitch("10.61", "meyer_foto")
    assert "включения в фарше" in AL.equipment_pitch("10.13", "meyer_rentgen")


def test_bez_svoey_gradacii_beryotsya_obshchaya_meyer():
    """Пустота хуже общей боли: письмо без «зачем» вырождается в рекламу."""
    assert AL.equipment_pitch("10.99", "meyer") == "общая боль пищёвки"


def test_osnovnoy_kod_pobezhdaet_dopolnitelnyy():
    """Если по основному коду боль есть — дополнительным её не подменяем."""
    боль, откуда = AL.боль_по_кодам(["25.62", "10.61"], "kc")
    assert боль == "сжатый воздух в цехе"
    # Возвращается код КОМПАНИИ (25.62), а не ключ таблицы (25): именно его
    # показывают в промпте, когда заход идёт от дополнительного кода.
    assert откуда == "25.62"


def test_dopolnitelnyy_kod_beryotsya_kogda_osnovnoy_pustoy():
    """Главное правило владельца: подходящий дополнительный ОКВЭД должен
    сработать, а не потеряться."""
    боль, откуда = AL.боль_по_кодам(["11.07", "10.61"], "kc")
    assert боль == "пневмотранспорт муки", боль
    assert откуда == "10.61"


def test_stroka_s_palkami_razbiraetsya():
    """Коды из карточки приезжают строкой «11.07|10.61» — это тоже вход."""
    боль, откуда = AL.боль_по_кодам("11.07|10.61", "kc")
    assert откуда == "10.61"


def test_blok_poluchatelya_govorit_pro_dopolnitelnyy_kod():
    """Читатель не должен думать, что мы ошиблись адресатом: если заход от
    дополнительного вида деятельности — это сказано прямо."""
    блок = AL._recipient_block(0, {"company_name": "ООО Вода",
                                   "okved": "11.07", "okved_all": "11.07|10.61"},
                               "kc", 0)
    assert "по дополнительному коду 10.61" in блок, блок


def test_nichego_ne_nashli_dayot_umolchanie():
    боль, откуда = AL.боль_по_кодам(["99.99"], "kc")
    assert боль == "сжатый воздух"
    assert откуда == ""


def test_imya_bez_zhivogo_istochnika_ne_ispolzuetsya():
    """Имя в карточке — не повод обращаться по имени.

    Сессия обогащения 11.08 замерила: у четверти контактов ссылка-источник уже
    не открывается, перепроверить имя нечем. Ошибиться именем в холодном
    письме дороже, чем написать «Добрый день!».
    """
    без_ссылки = AL._recipient_block(0, {
        "company_name": "ООО Завод", "okved": "25.62",
        "contact_name": "Иванов И. И.",
        "extra": {"contact_source": "own-site"}}, "kc", 0)
    assert "источник имени ненадёжен" in без_ссылки, без_ссылки
    assert "можно именное приветствие" not in без_ссылки

    со_ссылкой = AL._recipient_block(0, {
        "company_name": "ООО Завод", "okved": "25.62",
        "contact_name": "Иванов И. И.",
        "extra": {"contact_source": "own-site:staff",
                  "contact_source_url": "https://zavod.ru/staff/"}}, "kc", 0)
    assert "можно именное приветствие" in со_ссылкой, со_ссылкой


def test_kontakt_s_chuzhogo_sayta_zapreshchaet_upominat_sayt():
    """Адрес с общего сайта группы: получатель не узнает у себя ни страницу,
    ни текст, и «на вашем сайте» превращает письмо в очевидную рассылку."""
    блок = AL._recipient_block(0, {
        "company_name": "ООО Дочка", "okved": "25.62",
        "contact_name": "Петров П. П.",
        "extra": {"contact_source": "краул-соседа:holding.ru",
                  "contact_source_url": "https://holding.ru/contacts/"}}, "kc", 0)
    assert "с ЧУЖОГО сайта" in блок, блок
    assert "не упоминать сайт вовсе" in блок
    # И имя тоже не годится: источник не собственный сайт компании.
    assert "источник имени ненадёжен" in блок
