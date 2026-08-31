# -*- coding: utf-8 -*-
"""Как идёт отдельный прогон пробы."""
import glob
import io
import os
import sqlite3
import subprocess
import time

r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "(Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "Where-Object { $_.CommandLine -like '*probnut_partiyu*' }).Count"],
                   capture_output=True, text=True, timeout=90)
print("живых прогонов пробы: %s" % (r.stdout or "").strip())

for шаблон, имя in ((r"C:\sender\_ops\probnut_partiyu-*.log", "лог"),
                    (r"C:\sender\_ops\probnut_partiyu-*.err", "ошибки")):
    файлы = sorted(glob.glob(шаблон), key=os.path.getmtime, reverse=True)[:1]
    for п in файлы:
        размер = os.path.getsize(п)
        print("\n=== %s %s (%d Б, %.1f мин назад) ==="
              % (имя, os.path.basename(п), размер,
                 (time.time() - os.path.getmtime(п)) / 60.0))
        if размер:
            с = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
            for x in с[:3]:
                print("   %s" % x[:150])
            if len(с) > 12:
                print("   …")
            for x in с[-10:]:
                print("   %s" % x[:150])

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
без = c.execute(
    "SELECT COUNT(DISTINCT lower(trim(cr.email))) FROM confirm_reviews cr"
    " LEFT JOIN addr_probe p ON p.email = lower(trim(cr.email))"
    " WHERE cr.status IN ('pending','approved','edited')"
    "   AND COALESCE(cr.kind,'outbound') <> 'reply' AND p.email IS NULL"
).fetchone()[0]
сегодня = list(c.execute(
    "SELECT COALESCE(p.verdict,'ПРОБЫ НЕТ') в, COUNT(*) n"
    "  FROM confirm_reviews cr"
    "  LEFT JOIN addr_probe p ON p.email = lower(trim(cr.email))"
    " WHERE cr.campaign_id=11 AND cr.created_at >= datetime('now','-6 hour')"
    " GROUP BY в ORDER BY n DESC"))
снято = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=11"
                  "  AND status NOT IN ('pending','approved','edited','sent')"
                  "  AND created_at >= datetime('now','-6 hour')").fetchone()[0]
c.close()
print("\n=== СЕГОДНЯШНЯЯ ПАРТИЯ MEYER ===")
for в, n in сегодня:
    print("   %-18s %5d" % (в, n))
print("\n=== ИТОГ ===")
print("адресов очереди без пробы: %d" % без)
print("писем партии снято с очереди: %d" % снято)
