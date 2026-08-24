# -*- coding: utf-8 -*-
"""Работают ли правки после перезапуска панели: по делам, а не по файлам.

Смотрим три следа: журнал панели (строки probe_sync/addr_probe), снятые
пробой карточки с новыми причинами и остаток непроверенных одобренных
(было 66 без пробы и 10 с «неясно»).
"""
import glob
import io
import os
import sqlite3
import time

print("=== ЖИВА ЛИ ПАНЕЛЬ И ЧТО В ЖУРНАЛЕ ===")
логи = []
for корень in (r"C:\sender", r"C:\sender\logs", r"C:\sender\sender"):
    логи += glob.glob(os.path.join(корень, "*.log"))
логи = sorted(set(логи), key=lambda п: -os.path.getmtime(п))[:4]
for п in логи:
    возраст = (time.time() - os.path.getmtime(п)) / 60.0
    print("\n  %s (обновлён %.1f мин назад, %.0f КБ)"
          % (os.path.basename(п), возраст, os.path.getsize(п) / 1024.0))
    try:
        with io.open(п, encoding="utf-8", errors="replace") as ф:
            хвост = ф.readlines()[-4000:]
    except Exception as e:  # noqa: BLE001
        print("    не прочитан: %s" % e)
        continue
    интересно = [с for с in хвост
                 if "probe_sync" in с or "addr_probe" in с
                 or "цикл запущен" in с or "Started" in с or "Uvicorn" in с]
    for с in интересно[-14:]:
        print("    %s" % с.rstrip()[:190])
    if not интересно:
        print("    (строк про пробу нет)")

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("\n=== СНЯТЫЕ ПРОБОЙ КАРТОЧКИ (сегодня) ===")
есть = False
for р in c.execute(
        "SELECT decided_by, reason, COUNT(*) n, MAX(decided_at) t "
        "  FROM confirm_reviews "
        " WHERE status='skipped' AND substr(COALESCE(decided_at,''),1,10)=date('now') "
        "   AND COALESCE(decided_by,'') LIKE '%проба%' "
        " GROUP BY decided_by, substr(COALESCE(reason,''),1,28) "
        " ORDER BY t DESC LIMIT 12"):
    есть = True
    print("  %-34s %-46s %3d  последняя %s"
          % (str(р["decided_by"])[:34], str(р["reason"] or "")[:46], р["n"],
             str(р["t"])[:19]))
if not есть:
    print("  пока ничего не снято")

print("\n=== ЧТО ОСТАЛОСЬ В ОЧЕРЕДИ ===")
без_пробы = c.execute(
    "SELECT COUNT(*) n FROM confirm_reviews cr "
    "  JOIN recipients r ON r.id=cr.recipient_id "
    "  LEFT JOIN addr_probe p ON lower(p.email)=lower(r.email) "
    " WHERE cr.status='approved' AND p.email IS NULL").fetchone()["n"]
print("  одобренных без пробы вовсе: %d  (было 66)" % без_пробы)
for р in c.execute(
        "SELECT p.verdict, COUNT(*) n FROM confirm_reviews cr "
        "  JOIN recipients r ON r.id=cr.recipient_id "
        "  JOIN addr_probe p ON lower(p.email)=lower(r.email) "
        " WHERE cr.status IN ('approved','pending') "
        "   AND p.verdict IN ('неясно','нет ящика','нет MX') "
        " GROUP BY p.verdict ORDER BY n DESC"):
    print("  одобренных/ждущих с приговором «%s»: %d" % (р["verdict"], р["n"]))

print("\n=== СВЕЖИЕ ВЕРДИКТЫ ПРОБЫ (последние 10 минут) ===")
for р in c.execute(
        "SELECT verdict, source, COUNT(*) n, MAX(ts) t FROM addr_probe "
        " WHERE ts >= datetime('now','-10 minutes') GROUP BY verdict, source "
        " ORDER BY n DESC"):
    print("  %-16s [%-12s] %4d  последний %s"
          % (р["verdict"], str(р["source"] or "-"), р["n"], str(р["t"])[:19]))
