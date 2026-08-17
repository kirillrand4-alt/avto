# -*- coding: utf-8 -*-
"""Имя надёжно, если его подтверждает сам почтовый адрес (imya_ok).

Раньше имя считалось надёжным ТОЛЬКО при ссылке на страницу сотрудников
самой компании. Таких всего 381 компания (3 064 записи), и именных
приветствий из-за этого не было почти нигде: в партии 935 имя известно у 96
писем из 140 и использовано НОЛЬ раз.

Вторая улика самостоятельная: имя согласуется с написанием ящика
(a.demchenko@momez.ru ↔ А. Демченко), признак imya_ok в enrich.db/emails,
6 791 адрес. Решение владельца 17.08: засчитывать как достаточное.

Чего эта улика НЕ отменяет: общий ящик (приёмная, info@, бухгалтерия)
по-прежнему запрещает именное приветствие.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.ai_letter import _recipient_block  # noqa: E402

БАЗА = dict(company_name='ООО «Момез»', okved='25.62', activity='металл',
            mode='GENERIC', contact_name='Андрей Демченко')


def блок(**ex):
    r = dict(БАЗА)
    r['extra'] = dict(ex)
    return _recipient_block(0, r, 'kc', 0)


def test_bez_ulik_imya_ne_upominat():
    """Ни ссылки, ни imya_ok — прежнее поведение: имя не трогаем."""
    б = блок()
    assert 'источник имени ненадёжен' in б, б


def test_imya_ok_daet_imennoe_privetstvie():
    """Адрес подтвердил имя — можно здороваться по имени."""
    б = блок(imya_ok=True)
    assert 'можно именное приветствие' in б, б
    assert 'ненадёжен' not in б, б


def test_imya_ok_ne_otmenyaet_obshchiy_yashchik():
    """На приёмную по имени не здороваемся даже с подтверждённым именем."""
    б = блок(imya_ok=True, role='приёмная')
    assert 'по имени НЕ' in б, б
    assert 'передайте письмо ему' in б, б


def test_imya_ok_bez_imeni_nichego_ne_daet():
    """Признак есть, а имени нет — здороваться нечем."""
    r = dict(БАЗА)
    r['contact_name'] = ''
    r['extra'] = {'imya_ok': True}
    б = _recipient_block(0, r, 'kc', 0)
    assert 'нет имени' in б, б


def test_lozhnyy_priznak_ne_schitaetsya():
    """imya_ok=False/0/пусто — это не улика."""
    for v in (False, 0, '', None):
        б = блок(imya_ok=v)
        assert 'источник имени ненадёжен' in б, (v, б)


ТЕСТЫ = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    сбои = []
    for т in ТЕСТЫ:
        try:
            т()
            print(f"  ок   {т.__name__}")
        except Exception as ex:                                # noqa: BLE001
            сбои.append(т.__name__)
            print(f"  СБОЙ {т.__name__}: {type(ex).__name__} {ex}")
    print(f"\n{len(ТЕСТЫ) - len(сбои)} прошло, {len(сбои)} упало")
    sys.exit(1 if сбои else 0)
