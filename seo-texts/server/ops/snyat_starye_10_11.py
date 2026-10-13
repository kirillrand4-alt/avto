# -*- coding: utf-8 -*-
"""Снять 4 старых письма кампаний 10/11, висящих в расписании с 28.08 и 10.09.

Владелец 12.10 велел снять старые зависшие письма (#11, 18 штук); эти четыре
остались. auto_send не смотрит на статус кампании и выпустил бы их в окно
09:00 — письмо полуторамесячной давности. Статус skipped, причина в last_error.
"""
import sqlite3
from datetime import datetime, timezone
ИД = (12485, 12486, 12487, 18102)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
теперь = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
with c:
    n = c.execute(
        "UPDATE messages SET status='skipped', last_error=?, updated_at=? "
        "WHERE id IN (%s) AND status='scheduled' AND campaign_id IN (10, 11)" % ",".join("?" * len(ИД)),
        ("снято 13.10: старое письмо кампании 10/11 висело в расписании с августа/сентября",
         теперь) + ИД).rowcount
print("снято: %d" % n)
print("=== СТАРЫЕ 10/11 СНЯТЫ ===")
