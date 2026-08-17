# -*- coding: utf-8 -*-
"""Именное приветствие: решает ФОРМА имени, а не флаг imya_ok.

Сперва признаком надёжности взяли imya_ok из enrich.db — владелец разрешил
засчитывать его как достаточный. Замер 17.08 показал, что признак для этого
не годится, по двум причинам сразу.

1. Он не различает имя со страницы и имя, пересказывающее ящик. У всех
   7 097 записей стоит source=own-site и ссылка, но означает это, что на
   сайте нашли АДРЕС: a.demchenko@momez.ru -> «А. Демченко»,
   kochergin.m@vetin.su -> «М. Кочергин», nesterov.v@vetin.su ->
   «В. Нестеров». Поздороваться «Добрый день, А.!» нельзя, а «Добрый день,
   Демченко!» по-русски грубо.
2. До карточки флаг не доезжает вовсе: в contacts.emails лежат email,
   mx_ok, origin, person, role, source, source_url — и ничего больше. Правка
   по флагу работала вхолостую.

Форма имени различает надёжнее и берётся из поля, которое в карточке ЕСТЬ:
нужно не меньше двух ПОЛНЫХ слов. По базе 6 067 годных против 1 030
инициальных.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.ai_letter import _polnoe_imya, _recipient_block  # noqa: E402

БАЗА = dict(company_name='ООО «Момез»', okved='25.62', activity='металл',
            mode='GENERIC')

# Адрес по умолчанию согласуется с фамилией «Демченко» — второе условие
# именного приветствия (см. test_imya_i_yashchik.py) здесь выполнено всегда,
# чтобы тесты проверяли ровно ФОРМУ имени и ничего больше.
ЯЩИК = 'a.demchenko@momez.ru'


def блок(имя, email=ЯЩИК, **ex):
    r = dict(БАЗА)
    r['contact_name'] = имя
    r['extra'] = dict(ex, email=email)
    return _recipient_block(0, r, 'kc', 0)


# --- сам разбор формы имени ----------------------------------------------- #

def test_polnoe_imya_godится():
    assert _polnoe_imya('Анна Егорова')
    assert _polnoe_imya('Хачатрян Гоар Аветисовна')
    assert _polnoe_imya('Даутов Айдар Сиреневич')


def test_imya_iz_yashchika_ne_godится():
    """Именно эти формы пересказывают ящик — их отсекаем."""
    for плохое in ('А. Демченко', 'М. Кочергин', 'В. Нестеров',
                   'Халин В.В.', 'А.', 'Демченко'):
        assert not _polnoe_imya(плохое), плохое


def test_pustoe_i_musor():
    for x in ('', None, '   ', '123 456', 'ооо ромашка'):
        assert not _polnoe_imya(x), x


# --- как это видно в блоке получателя ------------------------------------- #

def test_polnoe_imya_daet_imennoe_privetstvie():
    б = блок('Андрей Демченко')
    assert 'можно именное приветствие' in б, б


def test_inicialy_imya_ne_upominat():
    б = блок('А. Демченко')
    assert 'источник имени ненадёжен' in б, б


def test_obshchiy_yashchik_silnee_polnogo_imeni():
    """На приёмную по имени не здороваемся даже с полным именем."""
    б = блок('Андрей Демченко', role='приёмная')
    assert 'по имени НЕ' in б, б
    assert 'передайте письмо ему' in б, б


def test_bez_imeni_bezlichno():
    б = блок('')
    assert 'нет имени' in б, б


ТЕСТЫ = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    сбои = []
    for т in ТЕСТЫ:
        try:
            т()
            print(f"  ок   {т.__name__}")
        except Exception as ex:                                # noqa: BLE001
            сбои.append(т.__name__)
            print(f"  СБОЙ {т.__name__}: {type(ex).__name__} {str(ex)[:120]}")
    print(f"\n{len(ТЕСТЫ) - len(сбои)} прошло, {len(сбои)} упало")
    sys.exit(1 if сбои else 0)
