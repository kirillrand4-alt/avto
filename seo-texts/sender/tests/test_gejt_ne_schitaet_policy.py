# -*- coding: utf-8 -*-
"""Гейт репутации не должен считать отбивкой отказ по политике.

Событие 'bounce' пишется и на «ящика нет», и на «550 5.7.1 blocked due to
security reason». Это разные вещи: в первом случае адрес мусорный и за такое
провайдеры режут домен, во втором ящик ЖИВОЙ, письмо завернул фильтр
получателя.

Замер 18.08: из четырёх ящиков, закрытых гейтом, два набрали свой процент
именно policy-отказами — 1 мёртвый + 2 policy на 50 писем даёт 6%, а честные
2.0% порога 2.5% не пробивают. Простой — 70 писем в день до конца месяца.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.store import Store  # noqa: E402

ЯЩИК = "a.balakirev@compressor-store.ru"


class _Пороги:
    """Боевые пороги 18.08: отбивок на ящик 2.5%, значимо с 50 писем."""
    domain_bounce_pct = 3.0
    domain_complaint_pct = 0.3
    mailbox_bounce_pct = 2.5
    global_complaint_pct = 0.1
    min_volume = 50
    provider_bounce_pct = 2.5
    window_days = 14


class _Конфиг:
    def gates(self):
        return _Пороги()

    def get(self, key, default=None):
        return default
СЕЙЧАС = datetime.now(timezone.utc)


def _база():
    п = os.path.join(tempfile.mkdtemp(), "sender.db")
    s = Store(п)
    s.init_schema()
    return s


def _событие(store, тип, i, вердикт=None, ящик=ЯЩИК):
    деталь = None
    if вердикт:
        деталь = json.dumps({"dsn": {"verdict": вердикт,
                                     "diagnostic": "тест"}}, ensure_ascii=False)
    with store._lock:
        store._conn.execute(
            "INSERT INTO events (dedup_key, event_type, event_ts, mailbox_id, "
            "detail_json, created_at) VALUES (?,?,?,?,?,?)",
            (f"{тип}-{i}-{ящик}", тип,
             (СЕЙЧАС - timedelta(hours=1)).isoformat(), ящик, деталь,
             СЕЙЧАС.isoformat()))
        store._conn.commit()


def _подготовить():
    store = _база()
    for i in range(50):
        _событие(store, "sent", i)
    _событие(store, "bounce", 100, "hard")
    _событие(store, "bounce", 101, "policy")
    _событие(store, "bounce", 102, "policy")
    return store


def test_policy_ne_schitaetsya_otbivkoy():
    store = _подготовить()
    все = store.count_events(event_type="bounce", mailbox_id=ЯЩИК)
    без = store.count_events(event_type="bounce", mailbox_id=ЯЩИК,
                             exclude_policy=True)
    assert все == 3 and без == 1, (все, без)


def test_otpravki_flag_ne_trogaet():
    """Флаг относится только к отбивкам: 'sent' считается как считался."""
    store = _подготовить()
    assert store.count_events(event_type="sent", mailbox_id=ЯЩИК,
                              exclude_policy=True) == 50


def test_gruppirovka_tozhe_bez_policy():
    store = _подготовить()
    г = store.count_events_grouped(by="mailbox_id",
                                   event_types=("sent", "bounce"),
                                   exclude_policy=True)
    assert г[ЯЩИК]["sent"] == 50, г
    assert г[ЯЩИК]["bounce"] == 1, г


def test_bez_flaga_povedenie_prezhnee():
    store = _подготовить()
    г = store.count_events_grouped(by="mailbox_id",
                                   event_types=("sent", "bounce"))
    assert г[ЯЩИК]["bounce"] == 3, г


def test_gejt_ne_zapiraet_yashchik_iz_za_policy():
    """Тот самый случай: 1 мёртвый + 2 policy на 50 писем — ящик работает."""
    from sender.gates import Gates

    store = _подготовить()
    g = Gates(config=_Конфиг(), store=store)
    d = g.check_mailbox(ЯЩИК)
    assert d.value == 2.0, d
    assert d.tripped is False, d


def test_tri_myortvyh_zapirayut_kak_i_ranshe():
    """Настоящие мёртвые адреса гейт по-прежнему ловит."""
    from sender.gates import Gates

    store = _база()
    for i in range(50):
        _событие(store, "sent", i)
    for i in range(3):
        _событие(store, "bounce", 200 + i, "hard")
    d = Gates(config=_Конфиг(), store=store).check_mailbox(ЯЩИК)
    assert d.value == 6.0 and d.tripped is True, d


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
