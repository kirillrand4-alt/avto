# -*- coding: utf-8 -*-
"""Цена годного письма по отраслям в прогоне образцов (_ops/partiya-obrazcy.json)."""
import io
import json
import sqlite3
from collections import Counter, defaultdict
ид = set(json.load(io.open(r"C:\sender\_ops\partiya-obrazcy.json", encoding="utf-8")))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
сег = {р[0]: р[1] for р in c.execute("SELECT id, segment FROM recipients WHERE id IN (%s)" % ",".join(map(str, ид)))}
цена, годн, поп, брак = defaultdict(float), Counter(), Counter(), defaultdict(Counter)
видели = set()
for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8", errors="replace"):
    try:
        z = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    rid = z.get("recipient_id")
    if rid not in ид or z.get("этап") != "итог" or z.get("день") != "2026-10-13":
        continue
    к = (rid, z.get("цена_$"), z.get("сек"))
    if к in видели:
        continue
    видели.add(к)
    о = сег.get(rid, "?")
    поп[о] += 1
    цена[о] += float(z.get("цена_$") or 0)
    if z.get("ок"):
        годн[о] += 1
    else:
        брак[о][str((z.get("брак") or ["?"])[0]).split(":")[0][:30]] += 1
отсев = Counter()
for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8", errors="replace"):
    if "предкласс_отсев" in с:
        try:
            z = json.loads(с)
        except Exception:  # noqa: BLE001
            continue
        r = c.execute("SELECT segment FROM recipients WHERE inn=? AND id IN (%s)" % ",".join(map(str, ид)), (z.get("inn"),)).fetchone()
        if r:
            отсев[r[0]] += 1
итого_ц, итого_г, итого_п = sum(цена.values()), sum(годн.values()), sum(поп.values())
print("%-32s %5s %5s %8s %9s  %s" % ("отрасль", "попыт", "годн", "$", "$/годное", "брак (главное)"))
for о in sorted(поп, key=lambda x: (цена[x] / годн[x]) if годн[x] else 99):
    print("%-32s %5d %5d %8.2f %9s  %s | предкласс снял %d" % (о[:32], поп[о], годн[о], цена[о],
          ("$%.3f" % (цена[о] / годн[о])) if годн[о] else "—", dict(брак[о].most_common(2)), отсев.get(о, 0)))
print("ИТОГО: попыток %d, годных %d, $%.2f, за годное $%.3f" % (итого_п, итого_г, итого_ц,
      итого_ц / итого_г if итого_г else 0))
print("=== ЦЕНА ОБРАЗЦОВ ===")
