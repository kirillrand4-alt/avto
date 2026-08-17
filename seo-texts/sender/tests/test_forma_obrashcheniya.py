# -*- coding: utf-8 -*-
"""Имя в промпте: не «можно», а готовая строка приветствия.

Замер 17.08 по кампании 10: имя прошло ВСЕ заслоны у 33 писем, а
поздоровалась модель по имени в двух. Владелец: «про имя вроде обсудили,
какие брать безопасно, но имён тоже не вижу в письмах». Причина не в
правилах отбора имён - в формулировке: строка «(можно именное приветствие)»
читается как «не обязательно», и модель по умолчанию писала «Добрый день!».

Правило теперь указание с готовым обращением, а считает его
_forma_obrashcheniya: гадать, как звать «Виноградского Павла Евгеньевича»,
модель не должна.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.ai_letter import _forma_obrashcheniya, _recipient_block  # noqa: E402

БАЗА = dict(company_name='ООО «Момез»', okved='25.62', activity='металл',
            mode='GENERIC')


def блок(имя, email):
    r = dict(БАЗА)
    r['contact_name'] = имя
    r['extra'] = {'email': email}
    return _recipient_block(0, r, 'kc', 0)


# --- сама форма обращения -------------------------------------------------- #

def test_familiya_imya_otchestvo():
    """Живые записи из партии: фамилия впереди."""
    assert _forma_obrashcheniya('Виноградский Павел Евгеньевич') == 'Павел Евгеньевич'
    assert _forma_obrashcheniya('Низамов Вадим Илдарович') == 'Вадим Илдарович'
    assert _forma_obrashcheniya('Илюшникова Елена Алексеевна') == 'Елена Алексеевна'


def test_imya_otchestvo_familiya():
    """Тот же приём при обратном порядке."""
    assert _forma_obrashcheniya('Сергей Иванович Гринько') == 'Сергей Иванович'


def test_dva_slova_bez_otchestva():
    assert _forma_obrashcheniya('Анна Ружицкая') == 'Анна'
    assert _forma_obrashcheniya('Плотников Дмитрий') == 'Дмитрий'
    assert _forma_obrashcheniya('Алексей Назаров') == 'Алексей'
    assert _forma_obrashcheniya('Юлия Бычкова') == 'Юлия'


def test_ne_razobrali_otdayom_kak_est():
    """Лучше полное ФИО, чем ошибка словом."""
    assert _forma_obrashcheniya('Ким Ли') == 'Ким Ли'


def test_pustoe():
    for x in ('', None, '   '):
        assert _forma_obrashcheniya(x) == ''


# --- как это видно в промпте ----------------------------------------------- #

def test_v_promt_uezzhaet_gotovaya_stroka():
    б = блок('Виноградский Павел Евгеньевич', 'vinogradskiy_pe@segezha-group.com')
    assert 'ОБЯЗАТЕЛЬНО поздоровайся по имени' in б, б
    assert 'Добрый день, Павел Евгеньевич!' in б, б


def test_familiyu_v_privetstvie_ne_tashchim():
    """«Добрый день, Виноградский!» по-русски грубо."""
    б = блок('Виноградский Павел Евгеньевич', 'vinogradskiy_pe@segezha-group.com')
    assert 'Добрый день, Виноградский' not in б, б


def test_imya_ne_proshlo_zaslon_ukazaniya_net():
    """Ящик имени не подтверждает — указания здороваться быть не должно."""
    б = блок('Горынин Андрей Сергеевич', 'mfz55@mail.ru')
    assert 'ОБЯЗАТЕЛЬНО поздоровайся' not in б, б


ТЕСТЫ = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    сбои = []
    for т in ТЕСТЫ:
        try:
            т()
            print(f"  ок   {т.__name__}")
        except Exception as ex:                                # noqa: BLE001
            сбои.append(т.__name__)
            print(f"  СБОЙ {т.__name__}: {type(ex).__name__} {str(ex)[:140]}")
    print(f"\n{len(ТЕСТЫ) - len(сбои)} прошло, {len(сбои)} упало")
    sys.exit(1 if сбои else 0)
