# -*- coding: utf-8 -*-
"""Отбивку на настоящее письмо проба перебивать не вправе.

История одного адреса, kk@vebfabrika.ru:
  11.08  проба сказала «принимает всё» — домен соглашается на любой ящик;
  17.08  туда ушло письмо и отбилось: «invalid mailbox. Local mailbox is
         unavailable». Мы записали «нет ящика» — приговор;
  18.08 04:45  работник проб спросил сервер ещё раз, тот снова ответил «приму»
         (код 250, он же catch-all), и запись стала «есть». Адрес вернулся в
         работу, приговор исчез.

Разница между источниками принципиальная: проба ЗАДАЁТ ВОПРОС и её обманывает
catch-all, а доставка ПОЛУЧАЕТ ОТВЕТ на реально отправленное письмо. Поэтому
запись пробы поверх приговора доставки не проходит — ни в базу, ни в ответ
probe(), по которому вызывающий решает, писать ли на адрес.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.addr_probe import (AddrProbe, ЕСТЬ, НЕТ_ЯЩИКА,  # noqa: E402
                               НЕЯСНО, ПРИНИМАЕТ_ВСЁ)

АДРЕС = "kk@vebfabrika.ru"


def _проба():
    п = os.path.join(tempfile.mkdtemp(), "sender.db")
    return AddrProbe(п, ttl_days=30, pause_sec=0.0)


def _приговор(п):
    assert п.prigovor_dostavki(
        АДРЕС, НЕТ_ЯЩИКА,
        "жёсткая отбивка: invalid mailbox. Local mailbox is unavailable",
        550)


def test_proba_ne_perebivaet_prigovor():
    п = _проба()
    _приговор(п)
    п._save(АДРЕС, ЕСТЬ, 250, "2.1.5 Ok", "mx.vebfabrika.ru")
    assert п.cached(АДРЕС)["verdict"] == НЕТ_ЯЩИКА


def test_save_govorit_chto_otklonil():
    п = _проба()
    _приговор(п)
    assert п._save(АДРЕС, ПРИНИМАЕТ_ВСЁ, 250, "приму", "mx") is False
    assert п._save("живой@example.org", ЕСТЬ, 250, "ok", "mx") is True


def test_dostavka_perebivaet_probu():
    """Обратный порядок: приговор ложится поверх «принимает всё»."""
    п = _проба()
    п._save(АДРЕС, ПРИНИМАЕТ_ВСЁ, 250, "приму любой", "mx")
    _приговор(п)
    з = п.cached(АДРЕС)
    assert з["verdict"] == НЕТ_ЯЩИКА
    assert з["source"] == "hard-bounce"


def test_dostavka_perebivaet_dostavku():
    """Вторая отбивка того же адреса записывается, а не отклоняется."""
    п = _проба()
    _приговор(п)
    assert п.prigovor_dostavki(АДРЕС, НЕТ_ЯЩИКА, "unknown user", 550) is True


def test_probe_vozvrashchaet_prigovor_a_ne_svoyo_est():
    """Вызывающий не должен получить «есть» на похороненный адрес."""
    п = _проба()
    _приговор(п)
    рез = п._вердикт_или_приговор(
        АДРЕС, {"email": АДРЕС, "verdict": ЕСТЬ, "code": 250},
        ЕСТЬ, 250, "2.1.5 Ok", "mx.vebfabrika.ru")
    assert рез["verdict"] == НЕТ_ЯЩИКА, рез


def test_neyasno_tozhe_ne_stiraet_prigovor():
    """Даже «неясно» не должно снимать приговор: это не новость об адресе."""
    п = _проба()
    _приговор(п)
    п._save(АДРЕС, НЕЯСНО, None, "сервер молчит", "")
    assert п.cached(АДРЕС)["verdict"] == НЕТ_ЯЩИКА


def test_kolonka_dopisyvaetsya_v_staruyu_tablicu():
    """Боевая база заведена без source — миграция обязана пройти по месту."""
    import sqlite3
    п = os.path.join(tempfile.mkdtemp(), "sender.db")
    c = sqlite3.connect(п)
    c.execute("CREATE TABLE addr_probe (email TEXT PRIMARY KEY, verdict TEXT "
              "NOT NULL, code INTEGER, answer TEXT, mx TEXT, ts TEXT NOT NULL)")
    c.execute("INSERT INTO addr_probe VALUES (?,?,?,?,?,?)",
              (АДРЕС, ПРИНИМАЕТ_ВСЁ, 250, "приму", "mx", "2026-08-11T10:00:00"))
    c.commit()
    c.close()
    пр = AddrProbe(п, ttl_days=30, pause_sec=0.0)
    assert пр.cached(АДРЕС)["verdict"] == ПРИНИМАЕТ_ВСЁ    # старое уцелело
    _приговор(пр)
    assert пр.cached(АДРЕС)["verdict"] == НЕТ_ЯЩИКА
    пр._save(АДРЕС, ЕСТЬ, 250, "ok", "mx")
    assert пр.cached(АДРЕС)["verdict"] == НЕТ_ЯЩИКА


def test_staraya_zapis_bez_istochnika_perezapisyvaetsya():
    """Приговор — только помеченный. Обычную запись пробы правим как раньше."""
    п = _проба()
    п._save(АДРЕС, НЕЯСНО, None, "сервер молчит", "")
    assert п._save(АДРЕС, ЕСТЬ, 250, "ok", "mx") is True
    assert п.cached(АДРЕС)["verdict"] == ЕСТЬ


ТЕСТЫ = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    сбои = []
    for т in ТЕСТЫ:
        try:
            т()
            print(f"  ок   {т.__name__}")
        except Exception as ex:                                # noqa: BLE001
            сбои.append(т.__name__)
            print(f"  СБОЙ {т.__name__}: {type(ex).__name__} {str(ex)[:200]}")
    print(f"\n{len(ТЕСТЫ) - len(сбои)} прошло, {len(сбои)} упало")
    sys.exit(1 if сбои else 0)
