# -*- coding: utf-8 -*-
"""Какая выручка у компаний, которых гейт назвал покупателями сегодня.

Проверяем две вещи сразу:
  1) как «покупатели» делятся на «от 30 млн» и «выручка не известна»;
  2) НЕ ПРОСОЧИЛСЯ ли кто-то ниже порога — это была бы дыра в фильтре.
Сводка в конце: pl_run отдаёт только хвост вывода.
"""
import sqlite3
from collections import Counter

ПОРОГ = 30_000_000

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=90)
s.row_factory = sqlite3.Row

# формат времени в таблице: ISO с «T» и сравнение со строкой datetime('now')
# дают ложное совпадение — смотрим глазами, а не на веру.
образцы = [r[0] for r in s.execute(
    "SELECT ts FROM target_verdicts ORDER BY rowid DESC LIMIT 3")]

# берём последние записи по rowid, а не по времени: rowid растёт монотонно
# и от формата даты не зависит.
всего = s.execute("SELECT COUNT(*) FROM target_verdicts").fetchone()[0]
# сегодняшний прогон начался на отметке ~13320 (замер 06:12: было 13320)
ГРАНИЦА = 13320
свежие = [dict(r) for r in s.execute(
    "SELECT inn, verdict, source, ts FROM target_verdicts "
    " WHERE rowid > ? ORDER BY rowid", (ГРАНИЦА,))]
s.close()

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=90)
выручка = {}
for и, в in e.execute("SELECT inn, revenue_rub FROM companies"):
    ц = "".join(c for c in str(и or "") if c.isdigit())
    if ц:
        выручка[ц] = в
e.close()

виды = Counter()
разрез = Counter()
ниже = []
источники = Counter()
for r in свежие:
    инн = "".join(c for c in str(r["inn"] or "") if c.isdigit())
    виды[r["verdict"]] += 1
    источники[r["source"]] += 1
    if r["verdict"] != "покупатель":
        continue
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

print("=" * 64)
print("=== СВОДКА: ВЫРУЧКА У «ПОКУПАТЕЛЕЙ» ===")
print("формат ts в таблице: %s" % (образцы or "?"))
print("вердиктов в таблице всего: %d; после границы %d: %d"
      % (всего, ГРАНИЦА, len(свежие)))
print("источники вердиктов: %s" % dict(источники))
print("")
print("вердикты свежей партии:")
for к, в in виды.most_common():
    print("   %-18s %6d" % (к, в))
print("")
print("«ПОКУПАТЕЛЬ» в разрезе выручки:")
для_итога = sum(разрез.values())
for к, в in разрез.most_common():
    доля = (100.0 * в / для_итога) if для_итога else 0
    print("   %-34s %6d  (%4.1f%%)" % (к, в, доля))
print("")
if ниже:
    print("ПРОСОЧИЛИСЬ НИЖЕ ПОРОГА: %d штук, примеры:" % len(ниже))
    for инн, в in ниже[:10]:
        print("   ИНН %-12s выручка %s руб" % (инн, format(в, ",d")))
else:
    print("Ниже порога не просочился НИ ОДИН — фильтр отработал.")
