# -*- coding: utf-8 -*-
"""Только чтение: отраслевой состав группы meyer-v30."""
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

ЯДРО = {"01", "03", "10", "11", "21"}
ИМЕНА = {"10": "пищевые продукты", "11": "напитки", "01": "сельхоз", "03": "рыба",
         "21": "фармацевтика", "25": "металлоизделия", "22": "резина/пластмасса",
         "20": "химия", "46": "оптовая торговля", "28": "машины",
         "24": "металлургия", "23": "стройматериалы", "17": "бумага",
         "13": "текстиль", "26": "электроника", "27": "электрооборудование",
         "16": "дерево", "32": "прочее производство", "08": "добыча"}

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

группы = store.recipient_groups().get("по_id") or {}
в_v30 = {rid for rid, gr in группы.items() if "meyer-v30" in (gr or [])}
print("=== ГРУППА meyer-v30: %d строк ===" % len(в_v30))

c = Counter()
инн = {}
for р in s.execute("SELECT id, inn, okved, company_name FROM recipients"):
    if р["id"] not in в_v30:
        continue
    o = str(р["okved"] or "").strip()
    раз = o.split(".")[0].zfill(2) if o and o.split(".")[0].isdigit() else "??"
    if str(р["inn"]) in инн:
        continue
    инн[str(р["inn"])] = раз
    c[раз] += 1

итого = sum(c.values())
ядро = sum(v for k, v in c.items() if k in ЯДРО)
print("  уникальных компаний: %d" % итого)
print("\n  разделы ОКВЭД:")
for k, v in c.most_common(16):
    метка = "  ЯДРО" if k in ЯДРО else ""
    print("     %-4s %-24s %5d (%4.1f%%)%s"
          % (k, ИМЕНА.get(k, "—"), v, 100.0 * v / итого, метка))

print("\n=== ИТОГ ===")
print("  в профиле Meyer (01,03,10,11,21): %d (%.0f%%)" % (ядро, 100.0 * ядро / итого))
print("  ВНЕ профиля                      : %d (%.0f%%)"
      % (итого - ядро, 100.0 * (итого - ядро) / итого))
print("  из них раздел 25 «металлоизделия» (как «Завод РМЗ»): %d" % c.get("25", 0))
