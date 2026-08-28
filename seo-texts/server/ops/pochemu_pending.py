# -*- coding: utf-8 -*-
"""Почему 171 карточка обеих партий висит в pending."""
import io
import json
import sqlite3
from collections import Counter

партии = {}
for ф, п in ((r"C:\sender\_ops\vtorye-adresa.jsonl", 1),
             (r"C:\sender\_ops\vtorye-adresa-2.jsonl", 2)):
    try:
        for с in io.open(ф, encoding="utf-8"):
            d = json.loads(с)
            if "review" in d:
                партии[int(d["review"])] = п
    except FileNotFoundError:
        pass
вердикт = {}
for ф in (r"C:\sender\_ops\sud-vtoryh.jsonl", r"C:\sender\_ops\sud-vtoryh-2.jsonl"):
    try:
        for с in io.open(ф, encoding="utf-8"):
            d = json.loads(с)
            вердикт[int(d["id"])] = str(d.get("verdikt") or "").replace(
                "o", "о").replace("p", "р")
    except FileNotFoundError:
        pass

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
зн = ",".join("?" * len(партии))
строки = c.execute(
    "SELECT id, inn, email, panel_json, campaign_id FROM confirm_reviews "
    " WHERE id IN (%s) AND status='pending'" % зн, list(партии)).fetchall()
c.close()
print("в pending: %d" % len(строки))

флаги = Counter()
верд = Counter()
примеры = {}
без_флага = []
for r in строки:
    верд[вердикт.get(int(r["id"]), "не судили")] += 1
    try:
        п = json.loads(r["panel_json"] or "{}") or {}
    except Exception:                                            # noqa: BLE001
        п = {}
    сф = п.get("stop_flags") or []
    держит = ((п.get("actions") or {}).get("confirm_hold"))
    if not сф and not держит:
        без_флага.append((int(r["id"]), r["email"],
                          вердикт.get(int(r["id"]), "не судили")))
        флаги["стоп-флага НЕТ"] += 1
        continue
    if not сф:
        флаги["confirm_hold без текста флага"] += 1
        continue
    for ф_ in сф:
        к = (ф_.get("code") if isinstance(ф_, dict) else str(ф_)) or "?"
        к = str(к)[:34]
        флаги[к] += 1
        примеры.setdefault(к, (int(r["id"]), r["email"], r["inn"]))
print("")
print("=== вердикт судьи у них ===")
for к, n in верд.most_common():
    print("   %-16s %4d" % (к, n))
print("")
print("=== стоп-флаги ===")
for к, n in флаги.most_common():
    print("   %-72s %4d" % (к, n))
print("")
print("=== примеры карточек с флагом ===")
for к, (i, e, инн) in list(примеры.items())[:6]:
    print("   rev %-6s %-28s ИНН %s" % (i, str(e)[:28], инн))
    print("      %s" % к)
if без_флага:
    print("")
    print("=== pending БЕЗ флага (%d) ===" % len(без_флага))
    for i, e, в in без_флага[:8]:
        print("   rev %-6s %-30s судья: %s" % (i, str(e)[:30], в))
