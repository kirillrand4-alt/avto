# -*- coding: utf-8 -*-
"""Есть ли в базе агро-компании: получатели, группа, обогащение, журнал."""
import io
import os
import sqlite3

ГРУППА = "Агро зерно 2026"
ИСТОЧНИК = "чеко-агро-2026"
ЖУРНАЛ = r"C:\sender\_ops\agro-zalito.jsonl"

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=120)
по_источнику = s.execute(
    "SELECT COUNT(*) FROM recipients WHERE source=?", (ИСТОЧНИК,)).fetchone()[0]
по_группе = s.execute(
    "SELECT COUNT(*) FROM recipients WHERE COALESCE(extra_json,'') LIKE ?",
    ("%%%s%%" % ГРУППА,)).fetchone()[0]
всего_получателей = s.execute("SELECT COUNT(*) FROM recipients").fetchone()[0]
s.close()

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
из_сбора = {str(r[0]) for r in c.execute(
    "SELECT inn FROM requisites WHERE src='checko-sbor-agro'")}
в_компаниях = 0
if из_сбора:
    ряды = c.execute("SELECT inn FROM companies").fetchall()
    в_компаниях = sum(1 for (и,) in ряды if str(и) in из_сбора)
c.close()

есть_журнал = os.path.exists(ЖУРНАЛ)
строк = 0
if есть_журнал:
    строк = sum(1 for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace")
                if с.strip())

print("=" * 74)
print("=== СВОДКА: ЗАЛИТЫ ЛИ АГРО-КОМПАНИИ ===")
print("получателей с источником «%s»: %d" % (ИСТОЧНИК, по_источнику))
print("получателей в группе «%s»:  %d" % (ГРУППА, по_группе))
print("получателей в панели всего:       %d" % всего_получателей)
print("")
print("компаний сбора Чеко в requisites: %d" % len(из_сбора))
print("из них заведено в companies:      %d" % в_компаниях)
print("")
print("журнал заливки %s: %s"
      % (os.path.basename(ЖУРНАЛ),
         ("%d строк" % строк) if есть_журнал else "НЕ СОЗДАВАЛСЯ"))
print("")
if по_источнику or по_группе or есть_журнал:
    print("ВЫВОД: что-то залито, надо разбираться")
else:
    print("ВЫВОД: НЕ ЗАЛИТО НИЧЕГО. Был только сухой прогон.")
