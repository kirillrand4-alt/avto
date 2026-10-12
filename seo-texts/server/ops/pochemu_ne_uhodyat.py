# -*- coding: utf-8 -*-
"""Почему одобренные письма не уходят (владелец 12.10: «нажал отправить 23»).

Смотрим решения оператора за сегодня, статусы писем в messages, ошибки
отправки, состояние кампании и ящиков.
"""
import json
import sqlite3
import sys
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
print("--- решения в очереди подтверждения за сегодня ---")
for р in c.execute(
        "SELECT campaign_id, status, COUNT(*) n FROM confirm_reviews "
        "WHERE substr(COALESCE(decided_at, updated_at),1,10) >= date('now','-1 day') "
        "GROUP BY campaign_id, status ORDER BY campaign_id"):
    print("   кампания %-4s %-10s %4d" % (р["campaign_id"], р["status"], р["n"]))

print("")
print("--- письма одобренные/отправленные сегодня: статус в messages ---")
стат = Counter()
ошибки = Counter()
примеры = []
for р in c.execute(
        "SELECT cr.id rid, cr.status rs, cr.email, cr.decided_at, cr.reason, "
        "       m.id mid, m.status ms, m.mailbox_id mb, m.last_error le, "
        "       m.attempt_count ac, m.sent_at sa, m.scheduled_at sch "
        "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
        " WHERE cr.status IN ('approved','edited','sent') "
        "   AND substr(COALESCE(cr.decided_at, cr.updated_at),1,10) >= date('now','-1 day') "
        " ORDER BY cr.decided_at DESC"):
    стат[(р["rs"], р["ms"])] += 1
    if р["le"]:
        ошибки[str(р["le"])[:120]] += 1
    if len(примеры) < 8:
        примеры.append(dict(р))
for (rs, ms), n in стат.most_common():
    print("   решение %-9s → письмо %-14s %4d" % (rs, ms, n))
print("")
print("--- ошибки отправки ---")
for т, n in ошибки.most_common(8):
    print("   %4d  %s" % (n, т))
print("")
print("--- примеры ---")
for р in примеры:
    print("   #%s %-30s решено %s | письмо %s %s ящик=%s попыток=%s sent=%s sched=%s"
          % (р["rid"], str(р["email"])[:30], str(р["decided_at"])[:16],
             р["mid"], р["ms"], р["mb"], р["ac"], str(р["sa"])[:16],
             str(р["sch"])[:16]))
    if р["reason"]:
        print("        причина: %s" % str(р["reason"])[:140])

print("")
print("--- кампании ---")
for р in c.execute("SELECT id, name, status FROM campaigns WHERE id >= 10"):
    print("   #%s %-28s %s" % (р["id"], р["name"], р["status"]))
print("")
print("--- настройки отправки ---")
for к in ("autosend_enabled", "autosend", "confirm_autosend", "paused",
          "global_pause", "send_paused"):
    р = c.execute("SELECT value FROM settings WHERE key=?", (к,)).fetchone() \
        if c.execute("SELECT name FROM sqlite_master WHERE name='settings'").fetchone() else None
    if р is not None:
        print("   %-20s = %s" % (к, str(р[0])[:80]))
print("=== ПОЧЕМУ НЕ УХОДЯТ ===")
