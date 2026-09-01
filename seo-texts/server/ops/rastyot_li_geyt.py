# -*- coding: utf-8 -*-
"""Растёт ли кэш вердиктов гейта — то есть работает он или стоит. Замер дважды."""
import io
import re
import sqlite3
import time

t = io.open(r"C:\sender\sender\target_gate.py", encoding="utf-8",
            errors="replace").read()
м = re.search(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", t)
таблица = м.group(1) if м else "target_gate"
print("таблица кэша гейта: %s" % таблица)

def замер():
    c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                        timeout=90)
    try:
        всего = c.execute("SELECT COUNT(*) FROM %s" % таблица).fetchone()[0]
        поля = [r[1] for r in c.execute("PRAGMA table_info(%s)" % таблица)]
        поле_ts = next((п for п in ("ts", "created_at", "updated_at")
                        if п in поля), None)
        свежих = 0
        разбивка = []
        if поле_ts:
            свежих = c.execute(
                "SELECT COUNT(*) FROM %s WHERE %s > datetime('now','-70 minutes')"
                % (таблица, поле_ts)).fetchone()[0]
            разбивка = c.execute(
                "SELECT verdict, COUNT(*) FROM %s "
                " WHERE %s > datetime('now','-70 minutes') GROUP BY verdict"
                % (таблица, поле_ts)).fetchall()
        return всего, свежих, разбивка, поля
    finally:
        c.close()

в1, с1, р1, поля = замер()
time.sleep(75)
в2, с2, р2, _ = замер()

print("")
print("=" * 62)
print("=== СВОДКА: ЖИВ ЛИ ГЕЙТ ===")
print("поля таблицы: %s" % ", ".join(поля))
print("вердиктов всего:      было %d -> стало %d  (+%d за 75 секунд)"
      % (в1, в2, в2 - в1))
print("вердиктов за 70 минут: было %d -> стало %d" % (с1, с2))
print("свежие вердикты по видам: %s" % (р2 or "нет поля времени"))
print("")
if в2 > в1:
    print("ВЫВОД: гейт РАБОТАЕТ, просто медленно — %d вердиктов за 75 с, "
          "это %.0f компаний в час." % (в2 - в1, (в2 - в1) * 48))
else:
    print("ВЫВОД: гейт СТОИТ — за 75 секунд ни одного нового вердикта.")
