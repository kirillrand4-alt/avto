# -*- coding: utf-8 -*-
"""Что из намеченного на сегодня осталось неотправленным - и почему.

Слот scheduled почти пуст (5 писем со старыми датами), значит очередь
сегодня разобрана: 146 писем ушло. Остальное стоит либо карточками на
подтверждении, либо одобренными карточками, у которых письмо так и не
уехало. Разделяем эти кучи и показываем причину по каждой.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.store import Store                                      # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
with store._lock:
    ряды = store._conn.execute(
        "SELECT cr.id rid, cr.status cst, cr.campaign_id, cr.reason, "
        "       COALESCE(cr.email,'') email, m.id mid, m.status mst, "
        "       substr(m.scheduled_at,1,16) слот, substr(cr.created_at,1,10) созд "
        "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id"
    ).fetchall()
пары = Counter(f"карточка={р[1]} письмо={р[6] or '-'}" for р in ряды)
print(f"карточек всего: {len(ряды)}\n")
for к, н in пары.most_common(14):
    print(f"  {н:>5}  {к}")

ждут = [р for р in ряды if str(р[1]) in ("approved", "edited")
        and str(р[6] or "") not in ("sent",)]
print(f"\nОДОБРЕНЫ, НО ПИСЬМО НЕ УШЛО: {len(ждут)}")
for к, н in Counter(f"камп{р[2]} письмо={р[6] or 'нет'} слот={str(р[7])[:10]}"
                    for р in ждут).most_common(12):
    print(f"  {н:>4}  {к}")
for р in ждут[:12]:
    print(f"   #{р[0]} камп{р[2]} {р[4]} письмо={р[5]} ({р[6]}) слот {р[7]} "
          f"| {str(р[3] or '')[:40]}")

ожид = [р for р in ряды if str(р[1]) == "pending"]
print(f"\nЖДУТ ПОДТВЕРЖДЕНИЯ: {len(ожид)}")
for к, н in Counter(f"камп{р[2]} создана {р[8]}" for р in ожид).most_common(10):
    print(f"  {н:>4}  {к}")
