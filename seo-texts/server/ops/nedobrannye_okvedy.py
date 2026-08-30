# -*- coding: utf-8 -*-
"""ОКВЭДы, по которым база НЕ ДОБРАНА: полные коды, а не разделы.

Считаем по каждому полному коду: сколько там покупателей и сколько компаний в
базе обзвона. Недобор = сколько компаний должно было бы быть в базе, если бы
её состав повторял состав покупателей, минус то, что есть.
"""
import sqlite3
from collections import Counter

СЕНДЕР = r"C:\sender\sender.db"
ОБЗВОН = r"C:\sender\obzvon-index.db"
ОБОГ = r"C:\sender\enrich.db"


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


def код(з):
    з = str(з or "").strip()
    if not з or not з[0].isdigit():
        return ""
    # «25.11 Производство…» → «25.11»; берём только код
    к = з.split()[0].strip().rstrip(".,;")
    return к if к and к[0].isdigit() else ""


c = sqlite3.connect("file:%s?mode=ro" % СЕНДЕР, uri=True, timeout=60)
сделки = {цифры(r[0]) for r in c.execute(
    "SELECT value FROM suppression WHERE reason='deal_in_progress' "
    "  AND scope='inn'")}
сделки.discard("")
c.close()

e = sqlite3.connect("file:%s?mode=ro" % ОБОГ, uri=True, timeout=60)
e.row_factory = sqlite3.Row
пок_код = {}
статус = {}
for r in e.execute("SELECT inn, okved_main, status FROM requisites "
                   " WHERE COALESCE(ogrn,'')<>''"):
    и = цифры(r["inn"])
    if и:
        пок_код[и] = код(r["okved_main"])
        статус[и] = str(r["status"] or "")
напр = {}
for r in e.execute("SELECT inn, division, okved FROM companies"):
    и = цифры(r["inn"])
    if и:
        напр[и] = str(r["division"] or "")
        пок_код.setdefault(и, код(r["okved"]))
e.close()

o = sqlite3.connect("file:%s?mode=ro" % ОБЗВОН, uri=True, timeout=60)
o.row_factory = sqlite3.Row
образцы = []
баз_код = Counter()
имена = {}
всего_базы = 0
for r in o.execute("SELECT okved_main, okved_all_codes, found_okveds FROM obzvon"):
    if len(образцы) < 3:
        образцы.append(dict(r))
    к = код(r["okved_main"])
    if к:
        баз_код[к] += 1
        всего_базы += 1
    # словарь код→название: в found_okveds коды идут с подписями
    для = str(r["found_okveds"] or "")
    if для and len(имена) < 4000:
        for часть in для.split("|"):
            часть = часть.strip()
            if "(" in часть and ";" in часть:
                к2 = часть.split("(")[0].strip()
                имя = часть.split(";", 1)[1].rstrip(")").strip()
                if к2 and к2[0].isdigit() and имя and к2 not in имена:
                    имена[к2] = имя[:46]
o.close()

пок = Counter(пок_код[и] for и in сделки
              if и in пок_код and пок_код[и]
              and статус.get(и, "ACTIVE") == "ACTIVE")
пок_n = sum(пок.values())
print("образец строки базы: okved_main=%r" % образцы[0]["okved_main"])
print("покупателей (действующих) с кодом: %d, компаний базы с кодом: %d"
      % (пок_n, всего_базы))
print("подписей ОКВЭД собрано: %d" % len(имена))

ряды = []
for к, k in пок.items():
    доля = k / пок_n
    ожидалось = доля * всего_базы
    есть = баз_код.get(к, 0)
    ряды.append((ожидалось - есть, к, k, доля * 100, есть,
                 100.0 * есть / всего_базы))
ряды.sort(key=lambda x: -x[0])

print()
print("=== ОКВЭДЫ, ПО КОТОРЫМ БАЗА НЕ ДОБРАНА (полные коды) ===")
print("%-9s %7s %7s %9s %9s  %s"
      % ("код", "покуп.", "в базе", "доля пок.", "недобор", "что это"))
for недобор, к, k, дп, есть, дб in ряды[:30]:
    if недобор <= 0:
        continue
    print("%-9s %7d %7d %8.1f%% %9d  %s"
          % (к, k, есть, дп, int(недобор), имена.get(к, "")[:44]))
print("\nсуммарный недобор по этим кодам: %d компаний"
      % int(sum(x[0] for x in ряды if x[0] > 0)))

print("\n=== ГДЕ БАЗА, НАОБОРОТ, ПЕРЕБРАНА (топ-10) ===")
пере = []
for к, есть in баз_код.most_common(400):
    k = пок.get(к, 0)
    ожидалось = (k / пок_n) * всего_базы if пок_n else 0
    пере.append((есть - ожидалось, к, k, есть))
пере.sort(key=lambda x: -x[0])
for избыток, к, k, есть in пере[:10]:
    print("   %-9s в базе %6d, покупателей %3d → лишних %6d  %s"
          % (к, есть, k, int(избыток), имена.get(к, "")[:40]))
