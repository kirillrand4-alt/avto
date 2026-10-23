# -*- coding: utf-8 -*-
"""Компаниям карточек, заблокированных гейтом направлений («кампания kc,
компании подходит meyer»), ставим метку базы обзвона «kc+meyer» (владелец
23.10: «добавить компаниям кс+мейер»). Гейт (ObzvonIndex.divisions) читает
obzvon.division из базы на каждом вызове — перезапуск не нужен. Только там,
где метка сейчас без kc. Журнал _ops/kc-plus-meyer.jsonl, --otkat.
    kc_plus_meyer.py [--primenit | --otkat]"""
import io
import json
import sqlite3
import sys

ЖУР = r"C:\sender\_ops\kc-plus-meyer.jsonl"
о = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=120)
if "--otkat" in sys.argv:
    з = [json.loads(s) for s in io.open(ЖУР, encoding="utf-8")]
    with о:
        for x in reversed(з):
            о.execute("UPDATE obzvon SET division=? WHERE inn=?", (x["bylo"], x["inn"]))
    print("откат:", len(з))
    sys.exit()
c = sqlite3.connect(r"C:\sender\sender.db")
ids = json.load(io.open(r"C:\sender\_ops\napr-nesovpadayut.json"))
инн = sorted({str(r[0]) for r in c.execute("SELECT inn FROM confirm_reviews WHERE id IN (%s)" % ",".join(map(str, ids)))
              if r[0]}) if ids else []
правки = []
for i in инн:
    r = о.execute("SELECT division FROM obzvon WHERE inn=?", (i,)).fetchone()
    if r is None:
        print("нет в базе обзвона:", i)
        continue
    было = str(r[0] or "")
    части = {p for p in было.split("+") if p}
    if "kc" in части:
        continue
    правки.append((i, было, "+".join(sorted(части | {"kc"}))))
print("компаний:", len(инн), "| меняем метку:", len(правки), правки[:5])
if "--primenit" in sys.argv:
    with о, io.open(ЖУР, "a", encoding="utf-8") as ж:
        for i, было, стало in правки:
            о.execute("UPDATE obzvon SET division=? WHERE inn=?", (стало, i))
            ж.write(json.dumps({"inn": i, "bylo": было, "stalo": стало}) + "\n")
    print("ПРИМЕНЕНО")
