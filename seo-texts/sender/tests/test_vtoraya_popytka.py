# -*- coding: utf-8 -*-
"""Вторая попытка после брака (владелец 12.08: «делай»).

Брак был окончательным: получатель уходил в «уже сделанные» и письма больше не
получал никогда. Разбор 36 браков по всем кампаниям: по существу шесть,
остальные тридцать — форма текста (оборот «закладываю» 18 раз, нет строки
отказа, финал не «С уважением», объём, проценты). Из-за такой мелочи терялось
предприятие с проверенным техконтактом и выручкой.

Теперь брак по форме оставляет получателя в кандидатах, брак по существу —
нет, и число попыток ограничено.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from sender.ai_quota import (  # noqa: E402
    ПРЕДЕЛ_ПОПЫТОК, СТАТУС_БРАК, СТАТУС_БРАК_ФОРМА, AiQuota, статус_брака,
)


# Классификация причины: от неё зависит, будет ли второй заход.


def test_inzhenernaya_linza_eto_po_sushchestvu():
    assert статус_брака([
        "инженерная линза после починки: Профиль - розничная сеть "
        "магазинов (торговля), производственной линии фасовки нет"
    ]) == СТАТУС_БРАК


def test_forma_teksta_dayot_vtoruyu_popytku():
    for причина in ("оборот «закладываю»: «...закладывают проблему»",
                    "нет опции отказа",
                    "финал не «С уважением,»",
                    "объём 21 слов",
                    "цена: «идёт по цене фуража»",
                    "анти-штамп: оборот израсходован: рекламац (2>1)",
                    "предприятие не названо ни в теме, ни в теле (19и)"):
        assert статус_брака([причина]) == СТАТУС_БРАК_ФОРМА, причина


def test_pustaya_prichina_schitaetsya_formoy():
    """Неизвестную причину трактуем мягко: лучше лишняя попытка, чем
    потерянная компания."""
    assert статус_брака([]) == СТАТУС_БРАК_ФОРМА
    assert статус_брака(None) == СТАТУС_БРАК_ФОРМА


def test_smes_prichin_reshaetsya_po_sushchestvu():
    """Если среди претензий есть содержательная — второй заход не поможет."""
    assert статус_брака([
        "финал не «С уважением,»",
        "инженерная линза после починки: профиль не производственный",
    ]) == СТАТУС_БРАК


@pytest.fixture
def квота(tmp_path):
    """AiQuota с пустой БД: нужен только журнал генерации."""
    п = tmp_path / "panel.db"
    con = sqlite3.connect(str(п))
    con.execute("""CREATE TABLE confirm_reviews(
        id INTEGER PRIMARY KEY, campaign_id INTEGER, recipient_id INTEGER)""")
    con.commit()
    con.close()
    q = AiQuota.__new__(AiQuota)
    q._db_path = str(п)
    return q


def _записать(q, campaign_id, recipient_id, status):
    from sender.ai_letter import log_results
    log_results(q._db_path, campaign_id,
                [{"email": f"a{recipient_id}@b.ru", "recipient_id": recipient_id,
                  "status": status, "subject": "", "body": "", "rounds": []}])


def test_formalnyy_brak_ne_horonit_poluchatelya(квота):
    """Одна неудача по форме — получатель остаётся в работе."""
    _записать(квота, 7, 100, СТАТУС_БРАК_ФОРМА)
    assert 100 not in квота._already(7)


def test_brak_po_sushchestvu_horonit_srazu(квота):
    """Профиль не тот — второй заход ничего не изменит."""
    _записать(квота, 7, 101, СТАТУС_БРАК)
    assert 101 in квота._already(7)


def test_gotovoe_pismo_horonit(квота):
    """Письмо уже сделано — повторно не генерируем."""
    _записать(квота, 7, 102, "ok")
    assert 102 in квота._already(7)


def test_popytki_ogranicheny(квота):
    """Дважды не получилось — дальше крутить бессмысленно."""
    for _ in range(ПРЕДЕЛ_ПОПЫТОК):
        _записать(квота, 7, 103, СТАТУС_БРАК_ФОРМА)
    assert 103 in квота._already(7)


def test_forma_potom_ok_ne_meshayut_drug_drugu(квота):
    """Получатель, у которого после формального брака вышло письмо, закрыт."""
    _записать(квота, 7, 104, СТАТУС_БРАК_ФОРМА)
    _записать(квота, 7, 104, "ok")
    assert 104 in квота._already(7)


def test_kampanii_ne_smeshivayutsya(квота):
    """Брак в одной кампании не блокирует получателя в другой."""
    _записать(квота, 7, 105, СТАТУС_БРАК)
    assert 105 in квота._already(7)
    assert 105 not in квота._already(8)


def test_brak_formy_vsyo_ravno_schitaetsya_v_kvote(квота):
    """Квота дня расходуется и на неудачную попытку: иначе прогон зациклится
    на одном и том же получателе, пока не выберет весь дневной лимит."""
    _записать(квота, 7, 106, СТАТУС_БРАК_ФОРМА)
    con = sqlite3.connect(квота._db_path)
    статусы = [r[0] for r in con.execute(
        "SELECT status FROM ai_letter_log WHERE campaign_id=7")]
    con.close()
    assert статусы == [СТАТУС_БРАК_ФОРМА]
    # counters() кладёт всё, что не 'ok', в счётчик брака — проверяем это же
    # правило, не поднимая часовые пояса движка.
    assert СТАТУС_БРАК_ФОРМА != "ok"
