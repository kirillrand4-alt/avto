# -*- coding: utf-8 -*-
"""Состояние автоотправки: включатель, окно, и почему 407 писем ждут."""
import sys
from collections import Counter
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.auto_send import ENABLED_KEY, window_from           # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
теперь = datetime.now(timezone.utc)

вкл = None
try:
    вкл = store.get_setting(ENABLED_KEY, False)
except Exception as ex:                                         # noqa: BLE001
    вкл = "ошибка: " + str(ex)[:60]
окно = window_from(store, cfg)

# на какие часы назначены ждущие
часы = Counter()
зоны = Counter()
with store._lock:
    for р in store._conn.execute(
            """SELECT m.scheduled_at, r.tz FROM messages m
                 LEFT JOIN recipients r ON m.recipient_id = r.id
                WHERE m.status='scheduled'"""):
        часы[str(р["scheduled_at"] or "?").replace("T", " ")[:13]] += 1
        зоны[str(р["tz"] or "?")] += 1
print("--- на какие часы назначены ждущие (топ-10) ---")
for к, в in sorted(часы.items())[:10]:
    print("   %s  %5d" % (к, в))
print("")
print("--- часовые зоны получателей ---")
for к, в in зоны.most_common(6):
    print("   %-20s %5d" % (к, в))

print("")
print("=" * 74)
print("=== ПОЧЕМУ ПИСЬМА ЖДУТ ===")
print("сейчас UTC: %s" % теперь.strftime("%Y-%m-%d %H:%M"))
print("включатель автоотправки (%s): %s" % (ENABLED_KEY, вкл))
print("окно отправки: %s" % окно)
