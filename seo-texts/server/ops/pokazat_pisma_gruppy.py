# -*- coding: utf-8 -*-
"""Письма группы + досье компании (владелец 22.10: «10 писем сделай и скинь
досье на них и сайт»). По каждому получателю группы: компания, ИНН, сайт,
адрес и должность, паспорт ФСА из extra, письмо (тема + тело без подписи)
или причина брака из журнала. Только чтение.
    pokazat_pisma_gruppy.py gruppa=c10 [zhurnal=путь]"""
import io
import json
import sqlite3
import sys
import os
import requests
_буф = io.StringIO()
_печ = print
print = lambda *a, **k: _печ(*a, file=_буф, **k)  # noqa: E731

ГР = {"c10": "ФСА v4 C проба", "c11b": "ФСА v4 C проба 2"}.get(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("gruppa=")), "c10"))
ЖУР = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("zhurnal=")), r"C:\sender\_ops\gen-v4c-proba.jsonl")
c = sqlite3.connect(r"C:\sender\sender.db")
брак = {}
try:
    for s in io.open(ЖУР, encoding="utf-8"):
        z = json.loads(s)
        if "ок" in z and not z.get("ок"):
            брак[str(z.get("inn"))] = "; ".join(map(str, z.get("брак") or []))[:400]
except OSError:
    pass
for rid, em, inn, имя, ex in c.execute("SELECT id, email, inn, company_name, extra_json FROM recipients WHERE extra_json LIKE ?",
                                       ("%" + ГР + "%",)):
    x = json.loads(ex or "{}")
    if ГР not in (x.get("gruppy") or []):
        continue
    print("\n" + "=" * 70)
    print("## %s\nИНН %s | выручка %s | адрес %s (%s)\nсайт: %s" % (имя, inn, x.get("revenue_rub"), em, x.get("dolzhnost"), x.get("site") or "—"))
    print("почему Meyer:", x.get("pochemu_meyer"))
    for k, v in (x.get("pasport_fsa") or {}).items():
        print("  • %s: %s" % (k, str(v)[:500]))
    r = c.execute("SELECT subject, body FROM confirm_reviews WHERE recipient_id=? ORDER BY id DESC LIMIT 1", (rid,)).fetchone()
    if r:
        print("\nТЕМА: %s\n\n%s" % (r[0], str(r[1]).split("\n\nС уважением,")[0]))
    else:
        print("\nПИСЬМА НЕТ:", брак.get(str(inn), "не дошло до генерации"))

requests.put(os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/") + "/pisma-gruppy.txt",
             data=_буф.getvalue().encode("utf-8"), headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=60)
_печ("на дроп: pisma-gruppy.txt,", len(_буф.getvalue()), "знаков")
