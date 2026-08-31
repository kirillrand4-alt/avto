# -*- coding: utf-8 -*-
"""Схема events и что там за виды, плюс какие кампании кц."""
import sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("events: %s" % ", ".join("%s:%s" % (r[1], r[2])
                              for r in c.execute("PRAGMA table_info(events)")))
print("\nвиды событий:")
for r in c.execute("SELECT event_type, COUNT(*) n "
                   "FROM events GROUP BY event_type ORDER BY n DESC LIMIT 20"):
    print("   %-20s %6d" % (r[0], r[1]))
print("\nобразец detail_json у reply:")
for r in c.execute("SELECT event_type, detail_json FROM events "
                   " WHERE event_type LIKE '%repl%' OR event_type LIKE '%otvet%' LIMIT 3"):
    print("   %s -> %s" % (r[0], str(r[1])[:300]))
print("\nlead_events: %s" % ", ".join("%s:%s" % (r[1], r[2])
      for r in c.execute("PRAGMA table_info(lead_events)")))
for r in c.execute("SELECT kind, COUNT(*) n FROM lead_events GROUP BY kind "
                   " ORDER BY n DESC LIMIT 15"):
    print("   lead_events.kind %-16s %6d" % (r[0], r[1]))
print("\nотправлено по кампаниям:")
for r in c.execute("SELECT m.campaign_id, c2.name, COUNT(*) n FROM messages m "
                   " LEFT JOIN campaigns c2 ON c2.id=m.campaign_id "
                   " WHERE m.sent_at IS NOT NULL GROUP BY m.campaign_id "
                   " ORDER BY n DESC"):
    print("   %-4s %-34s %6d" % (r[0], (r[1] or "")[:34], r[2]))
c.close()
