# -*- coding: utf-8 -*-
"""Факты для инструкции: кампании, сегменты, ящики, пороги, состояние очереди."""
import sqlite3
import sys
sys.path.insert(0, r"C:\sender")
БАЗА = r"C:\sender\sender.db"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("=== КАМПАНИИ ===")
for r in c.execute("SELECT * FROM campaigns ORDER BY id"):
    d = dict(r)
    print("   %2s | %-36s | %s" % (d.get("id"), str(d.get("name"))[:36],
          {k: v for k, v in d.items() if k not in ("id", "name") and v}))
print("\n=== СЕГМЕНТЫ ПОЛУЧАТЕЛЕЙ (топ) ===")
for r in c.execute("SELECT segment, COUNT(*) n FROM recipients "
                   " GROUP BY 1 ORDER BY 2 DESC LIMIT 12"):
    print("   %-30s %d" % (str(r["segment"])[:30], r["n"]))
print("\n=== ОЧЕРЕДЬ СЕЙЧАС ===")
for r in c.execute("SELECT status, COUNT(*) n FROM confirm_reviews "
                   " GROUP BY 1 ORDER BY 2 DESC"):
    print("   confirm_reviews %-16s %d" % (r["status"], r["n"]))
for r in c.execute("SELECT status, COUNT(*) n FROM messages GROUP BY 1 "
                   " ORDER BY 2 DESC"):
    print("   messages        %-16s %d" % (r["status"], r["n"]))
c.close()
from sender.config import Config                                   # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
print("\n=== ЯЩИКИ ПО НАПРАВЛЕНИЯМ ===")
по = {}
for м in cfg.mailboxes():
    н = getattr(м, "division", "?") or "?"
    по.setdefault(н, []).append(getattr(м, "mailbox_id", "?"))
for н, я in по.items():
    print("   %-8s %d: %s" % (н, len(я), ", ".join(я[:3]) + " …"))
print("\n=== КЛЮЧЕВЫЕ НАСТРОЙКИ ===")
for ключ in ("confirm.live_send", "confirm.enabled", "ai.quota_per_day",
             "ai.model", "ai.batch", "orchestrator.active_campaigns",
             "orchestrator.send_batch", "gates.otkaz_stop_yashchik",
             "gates.otkaz_stop_napravlenie", "window.start", "window.end",
             "service.dry_run", "probe_enrich.zhivye_tolko"):
    try:
        print("   %-34s = %r" % (ключ, cfg.get(ключ, None)))
    except Exception as ex:
        print("   %-34s ? %s" % (ключ, ex))
