# -*- coding: utf-8 -*-
"""Просьба сменить заход обязана называть запрещённые слова поимённо.

Замер ночного прогона 17.08: из 60 последних писем 9 забраковано правилом
«заход "от профиля" израсходован на партии», и все девять начинались тем же
«Смотрел профиль…». Просьбу модель видела - в промпте стояло «начни
по-другому, по назначенной механике». Не сработало ни разу: модель не знает,
какие слова заслон считает той же формой, а заслон знает - он проверяет
регексом _ФОРМЫ_ЗАХОДА.

Цена промаха прямая: письмо написано и оплачено, а в панель не попало.

Поэтому промпт обязан перечислять ровно те слова, которые ловит заслон, и
давать замену - запрет без замены модель обходит вкруговую.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.ai_letter import (_ЗАПРЕТ_ЗАХОДА, _ФОРМЫ_ЗАХОДА,  # noqa: E402
                              _recipient_block, форма_захода)

БАЗА = dict(company_name='ООО «Момез»', okved='25.62', activity='металл',
            mode='GENERIC', contact_name='')


def блок(сменить):
    r = dict(БАЗА)
    r['extra'] = {'сменить_заход': сменить, 'email': 'a@momez.ru'}
    return _recipient_block(0, r, 'kc', 0)


def test_kazhdaya_forma_zaslona_imeet_zapret():
    """Списки обязаны совпадать: разъедутся - промпт просит не то, что гейт."""
    формы = {имя for имя, _rx in _ФОРМЫ_ЗАХОДА}
    assert формы == set(_ЗАПРЕТ_ЗАХОДА), (формы, set(_ЗАПРЕТ_ЗАХОДА))


def test_zapret_nazyvaet_slova_kotorye_lovit_zaslon():
    """«Смотрел» в запрете - и это же слово ловит регекс формы."""
    запрет, _вместо = _ЗАПРЕТ_ЗАХОДА['от профиля']
    for слово in ('Смотрел', 'Изучил', 'Глянул', 'Судя по'):
        assert слово in запрет, слово
    # и наоборот: то, что названо запретом, заслон действительно бракует
    assert форма_захода('Смотрел профиль «Момез» - вы режете металл.') \
        == 'от профиля'


def test_v_promt_uezzhayut_i_zapret_i_zamena():
    б = блок('от профиля')
    assert 'израсходован' in б, б
    assert 'Смотрел' in б, б
    assert 'Вместо этого' in б, б


def test_zamena_ne_pustaya_ni_u_odnoy_formy():
    for форма, (_з, вместо) in _ЗАПРЕТ_ЗАХОДА.items():
        assert len(вместо) > 20, (форма, вместо)


def test_zamena_sama_ne_narushaet_zapret():
    """Совет «начни так-то» не должен предлагать ту же запрещённую форму."""
    for форма, (_з, вместо) in _ЗАПРЕТ_ЗАХОДА.items():
        for пример in re.findall(r'«([^»]+)»', вместо):
            assert форма_захода(пример) != форма, (форма, пример)


def test_neizvestnaya_forma_ne_ronyaet_promt():
    """Форму опознают и по первым двум словам — запрета на неё нет."""
    б = блок('мы работаем')
    assert 'израсходован' in б, б
    assert 'начни с другой мысли' in б, б


def test_bez_podskazki_stroki_net():
    r = dict(БАЗА)
    r['extra'] = {'email': 'a@momez.ru'}
    assert 'израсходован' not in _recipient_block(0, r, 'kc', 0)


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
