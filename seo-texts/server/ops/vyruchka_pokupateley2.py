# -*- coding: utf-8 -*-
"""Вердикты ИМЕННО сегодняшнего прогона (старт 05:26 местного = 02:26 UTC).

Время разбираем питоном, а не строковым сравнением в SQLite: ts здесь ISO
с «T» и зоной, а datetime('now') даёт пробел — сравнение строк совпадает со
ВСЕЙ таблицей. Именно так у меня и вышли ложные «1 545 вердиктов».
"""
import sqlite3
from collections import Counter
from datetime import datetime, timezone

ПОРОГ = 30_000_000
СТАРТ = datetime(2026, 9, 1, 2, 26, 0, tzinfo=timezone.utc)   # 05:26 местного


def разобрать(з):
    try:
        d = datetime.fromisoformat(str(з))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:                                          # noqa: BLE001
        return None


s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=90)
строки = list(s.execute("SELECT inn, verdict, source, ts FROM target_verdicts"))
s.close()

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=90)
выручка = {}
for и, в in e.execute("SELECT inn, revenue_rub FROM companies"):
    ц = "".join(c for c in str(и or "") if c.isdigit())
    if ц:
        выручка[ц] = в
e.close()

виды, разрез, источники = Counter(), Counter(), Counter()
ниже = []
свежих = 0
for инн_с, вердикт, источник, ts in строки:
    d = разобрать(ts)
    if not d or d < СТАРТ:
        continue
    свежих += 1
    виды[вердикт] += 1
    источники[источник] += 1
    if вердикт != "покупатель":
        continue
    инн = "".join(c for c in str(инн_с or "") if c.isdigit())
    в = выручка.get(инн)
    if инн not in выручка:
        разрез["в обогащении нет вовсе"] += 1
    elif в is None or int(в or 0) == 0:
        разрез["выручка не известна (0 или NULL)"] += 1
    elif int(в) >= ПОРОГ:
        разрез["от 30 млн"] += 1
    else:
        разрез["НИЖЕ 30 млн — просочился"] += 1
        ниже.append((инн, int(в)))

# для сравнения: та же разбивка по ВСЕЙ таблице за всё время
всего_виды = Counter(в for _, в, _, _ in строки)

print("=" * 64)
print("=== СВОДКА: ВЕРДИКТЫ СЕГОДНЯШНЕГО ПРОГОНА (с 05:26) ===")
print("в таблице всего вердиктов: %d, из них сегодняшнего прогона: %d"
      % (len(строки), свежих))
print("источники: %s" % dict(источники))
print("")
print("вердикты прогона:")
for к, в in виды.most_common():
    print("   %-18s %6d" % (к, в))
print("")
print("«ПОКУПАТЕЛЬ» в разрезе выручки:")
итого = sum(разрез.values())
for к, в in разрез.most_common():
    print("   %-34s %6d  (%4.1f%%)"
          % (к, в, (100.0 * в / итого) if итого else 0))
print("")
if ниже:
    print("ПРОСОЧИЛИСЬ НИЖЕ ПОРОГА: %d, примеры:" % len(ниже))
    for инн, в in ниже[:10]:
        print("   ИНН %-12s %s руб" % (инн, format(в, ",d")))
else:
    print("Ниже порога не просочился НИ ОДИН — фильтр отработал.")
print("")
print("для сравнения, ВСЯ таблица за всё время: %s" % dict(всего_виды))
