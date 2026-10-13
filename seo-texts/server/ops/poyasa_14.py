# -*- coding: utf-8 -*-
"""Часовые пояса получателей писем кампании 14 в расписании.

Владелец 13.10: «а часовой пояс правильно определён? странно, что почти все
компании Москва». Смотрим: окно кампании (по поясу получателя или нет), поле
recipients.tz, и чем его можно восполнить — регион в enrich (адрес/регион)
и код региона в ИНН (первые две цифры — регион постановки на учёт).
"""
import json
import sqlite3
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
к = c.execute("SELECT config_json FROM campaigns WHERE id=14").fetchone()
try:
    кф = json.loads(к["config_json"] or "{}")
except Exception:  # noqa: BLE001
    кф = {}
print("окно кампании 14: %s" % json.dumps({x: кф.get(x) for x in кф if "window" in x or "tz" in x or "okno" in x},
                                          ensure_ascii=False)[:300])
строки = [dict(р) for р in c.execute(
    "SELECT m.id, m.scheduled_at, r.inn, r.tz, r.extra_json FROM messages m "
    "JOIN recipients r ON r.id=m.recipient_id WHERE m.campaign_id=14 AND m.status='scheduled'")]
print("в расписании: %d" % len(строки))
print("recipients.tz: %s" % dict(Counter(р["tz"] or "(пусто)" for р in строки).most_common(8)))
print("срок (час UTC): %s" % dict(Counter(str(р["scheduled_at"])[:13] for р in строки).most_common(6)))
коды = Counter(str(р["inn"] or "")[:2] for р in строки)
print("код региона по ИНН (топ): %s" % dict(коды.most_common(25)))
print("=== ПОЯСА 14 ===")
нули = [р for р in строки if str(р["inn"] or "")[:2] == "00"][:5]
for р in нули:
    try:
        д = json.loads(р["extra_json"] or "{}")
    except Exception:  # noqa: BLE001
        д = {}
    print("   ИНН %s | группы %s | ключи %s" % (р["inn"], д.get("gruppy"), ",".join(list(д)[:10])))
