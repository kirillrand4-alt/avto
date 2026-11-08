# -*- coding: utf-8 -*-
"""51 компания «КЦ по имени» со снятой «общей фразой»: что о них есть (enrich, база обзвона, лист «Работа» FSA, сайт)."""
import io, os, sqlite3, collections
import openpyxl
s = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
e = sqlite3.connect("file:C:\\sender\\enrich.db?mode=ro", uri=True, timeout=30)
o = sqlite3.connect("file:C:\\sender\\obzvon-index.db?mode=ro", uri=True, timeout=30)
инн = [str(r[0]) for r in s.execute("SELECT cr.inn FROM confirm_reviews cr JOIN campaigns c ON c.id=cr.campaign_id WHERE c.name='КЦ по имени 06.11' AND cr.status='skipped' AND cr.reason LIKE 'общая фраза%'")]
раб = {}
wb = openpyxl.load_workbook(r"C:\sender\_ops\FSA-MEYER-v4-KC.xlsx", read_only=True)
rows = wb["Работа"].iter_rows(values_only=True); h = list(next(rows))
for r in rows: раб[str(r[h.index("ИНН")] or "")] = (r[h.index("Компания")], r[h.index("Продукция (кратко)")], r[h.index("Сайт")])
сч = collections.Counter()
for i in инн:
    ен = e.execute("SELECT name, okved, length(COALESCE(activity,'')) FROM companies WHERE inn=?", (i,)).fetchone()
    об = o.execute("SELECT name_short, okved_main, sites FROM obzvon WHERE inn=?", (i,)).fetchone()
    рб = раб.get(i)
    сч["в enrich"] += bool(ен); сч["в обзвоне"] += bool(об); сч["в листе Работа"] += bool(рб)
    сч["есть продукция в файле"] += bool(рб and рб[1]); сч["есть ОКВЭД в обзвоне"] += bool(об and об[1]); сч["есть сайт"] += bool((рб and рб[2]) or (об and об[2]))
print("компаний:", len(инн), dict(сч))
for i in инн[:8]:
    рб = раб.get(i, ("", "", "")); об = o.execute("SELECT okved_main, sites FROM obzvon WHERE inn=?", (i,)).fetchone()
    print("  ", i, "|", str(рб[0])[:40], "|", str(рб[1])[:80], "|", (об[0] if об else ""), "|", str(рб[2] or (об[1] if об else ""))[:40])
