# -*- coding: utf-8 -*-
"""Доля отказов «спам» по версиям текста письма.

Отправленные письма хранят СВОЙ текст (body_rendered у них не перезаписывался),
поэтому каждое ушедшее письмо можно отнести к версии и посчитать честно.
"""
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

store = Store(r"C:\sender\sender.db")
ВЕРСИИ = (("новый список задач", "удаление эгилопса и овсюга"),
          ("решето и аспирация", "решето и аспирация не закрывают"),
          ("доведение до качества", "доведения товарных партий"))


def версия(т):
    for имя, метка in ВЕРСИИ:
        if метка in (т or ""):
            return имя
    return "другой текст"


ушло = Counter()
отказ = Counter()
with store._lock:
    кол = [c[1] for c in store._conn.execute("PRAGMA table_info(events)")]
    вр = next((c for c in ("ts", "created_at", "occurred_at") if c in кол), None)
    тп = next((c for c in ("type", "kind", "event_type") if c in кол), None)
    мид = next((c for c in ("message_id", "msg_id") if c in кол), None)
    print("events: время=%s тип=%s письмо=%s" % (вр, тп, мид))
    for р in store._conn.execute(
            "SELECT body_rendered FROM messages WHERE status='sent' "
            "  AND sent_at >= datetime('now','-3 days') AND campaign_id=11"):
        ушло[версия(str(р["body_rendered"] or ""))] += 1
    if мид:
        for р in store._conn.execute(
                "SELECT m.body_rendered FROM events e "
                "  JOIN messages m ON m.id = e.%s "
                " WHERE e.%s='reject_spam' AND e.%s >= datetime('now','-3 days')"
                % (мид, тп, вр)):
            отказ[версия(str(р["body_rendered"] or ""))] += 1
    else:
        print("в событиях нет ссылки на письмо — отказы по версиям не свести")

print("")
print("=" * 74)
print("=== ОТКАЗЫ ПО ВЕРСИЯМ ТЕКСТА (3 дня, кампания Meyer) ===")
for имя, _м in ВЕРСИИ + (("другой текст", ""),):
    у, о = ушло.get(имя, 0), отказ.get(имя, 0)
    if not (у or о):
        continue
    доля = (100.0 * о / (у + о)) if (у + о) else 0
    print("   %-24s ушло %5d  отказов %4d  доля %.1f%%" % (имя, у, о, доля))
print("итого ушло %d, отказов %d" % (sum(ушло.values()), sum(отказ.values())))
