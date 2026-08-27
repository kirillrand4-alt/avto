# -*- coding: utf-8 -*-
"""Дневные лимиты ящиков против того, что уже ушло и что ждёт."""
import json
import sqlite3
from datetime import datetime, timezone

c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row
лим = json.loads(c.execute("SELECT value FROM panel_settings "
                           " WHERE key='send_limits'").fetchone()[0])
общий = лим.get("all")
по_ящикам = лим.get("per_mailbox") or {}
print("общий лимит: %s" % (общий if общий is not None else "нет"))

сегодня = datetime.now(timezone.utc).strftime("%Y-%m-%d")
ушло = {r["mailbox_id"]: r["n"] for r in c.execute(
    "SELECT mailbox_id, COUNT(*) n FROM messages "
    " WHERE substr(sent_at,1,10)=? GROUP BY mailbox_id", (сегодня,))}
ждут = {r["mailbox_id"]: r["n"] for r in c.execute(
    "SELECT mailbox_id, COUNT(*) n FROM messages "
    " WHERE status IN ('scheduled','sending') GROUP BY mailbox_id")}

print("")
print("%-42s %6s %6s %7s %s" % ("ящик", "лимит", "ушло", "ждут", "хватит?"))
итог = [0, 0, 0]
беда = []
# Часть писем ушла без ящика (mailbox_id NULL) — их сортировать нельзя.
без_ящика = ушло.pop(None, 0) + ждут.pop(None, 0)
if без_ящика:
    print("писем без ящика: %d" % без_ящика)
for я in sorted(set(list(ушло) + list(ждут) + list(по_ящикам))):
    л = по_ящикам.get(я, общий)
    у, ж = ушло.get(я, 0), ждут.get(я, 0)
    итог[0] += (л or 0)
    итог[1] += у
    итог[2] += ж
    если = ("лимит 0 — НЕ ПОЙДЁТ" if л == 0 else
            "хватит" if л is None or у + ж <= л else
            "не хватит на %d" % (у + ж - л))
    if л == 0 or (л is not None and у + ж > л):
        беда.append((я, л, у, ж))
    print("%-42s %6s %6d %7d %s" % (str(я)[:42], л if л is not None else "нет",
                                    у, ж, если))
print("")
print("итого: ушло %d, ждут %d" % (итог[1], итог[2]))
if беда:
    print("")
    print("=== чьи письма сегодня не уйдут ===")
    for я, л, у, ж in беда:
        print("   %-42s лимит %s, ушло %d, ждут %d" % (str(я)[:42], л, у, ж))
c.close()
