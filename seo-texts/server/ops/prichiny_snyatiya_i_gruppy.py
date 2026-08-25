# -*- coding: utf-8 -*-
"""Группы получателей и разбор причин снятия: что можно перегенерировать.

Владелец: «включая скипы — где причина не то что мы уже писали, а то что
письмо тогда не нравилось». Значит причины надо разложить на три кучи:
компания не наша (перегенерация не поможет), письмо было плохое (поможет),
писать некуда или незачем (не трогаем).
"""
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
группы = store.recipient_groups().get("по_id") or {}
размер = Counter()
for _rid, gr in группы.items():
    for г in (gr if isinstance(gr, (list, tuple, set)) else [gr]):
        размер[str(г)] += 1
print("=== ГРУППЫ ПОЛУЧАТЕЛЕЙ ===")
for г, н in размер.most_common(12):
    print("   %-38s %6d" % (г, н))

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
сегодня = {р[0] for р in c.execute(
    "SELECT id FROM recipients WHERE substr(created_at,1,10)=date('now')")}
в_группах = sum(1 for rid in сегодня if rid in группы)
print("\nзаведено сегодня: %d, из них в группах: %d" % (len(сегодня), в_группах))
if сегодня:
    их_группы = Counter()
    for rid in сегодня:
        for г in (группы.get(rid) or ["БЕЗ ГРУППЫ"]):
            их_группы[str(г)] += 1
    for г, н in их_группы.most_common(6):
        print("   %-38s %6d" % (г, н))

КАЧЕСТВО = re.compile(
    r"линз|правило \d|человечн|реклама|структур|зачин|механическ|"
    r"стиль|штамп|тема пуст|два знака|брак", re.I)
КОМПАНИЯ = re.compile(
    r"не наш|вне профиля|не покупател|минус-класс|направлени|не та тема|"
    r"не наша тема|занятие|напитки|конкурент|мульти-инн", re.I)
НЕ_ТРОГАТЬ = re.compile(
    r"уже писали|ответил|отпис|suppress|стоп|сделка|адрес|ящик|mx|проба|"
    r"опечатк|bulk-to-auto|deal_in_progress|бухгалтер", re.I)


def куча(п):
    п = str(п or "")
    if НЕ_ТРОГАТЬ.search(п):
        return "не трогаем"
    if КАЧЕСТВО.search(п):
        return "ПИСЬМО БЫЛО ПЛОХОЕ — можно перегенерировать"
    if КОМПАНИЯ.search(п):
        return "компания не наша — перегенерация не поможет"
    return "прочее: " + п[:40]


кучи = Counter()
инн_по_кучам = {}
for р in c.execute(
        "SELECT COALESCE(cr.reason,'') причина, r.inn "
        "  FROM confirm_reviews cr LEFT JOIN recipients r ON r.id=cr.recipient_id "
        " WHERE cr.status='skipped'"):
    к = куча(р["причина"])
    кучи[к] += 1
    if р["inn"]:
        инн_по_кучам.setdefault(к, set()).add(str(р["inn"]))
print("\n=== ПРИЧИНЫ СНЯТИЯ КАРТОЧЕК ===")
for к, н in кучи.most_common(12):
    print("   %-52s карточек %5d, фирм %5d"
          % (к[:52], н, len(инн_по_кучам.get(к, ()))))
