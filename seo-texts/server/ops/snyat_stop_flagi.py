# -*- coding: utf-8 -*-
"""Снять ложные стоп-флаги с карточек на подтверждении (владелец 16.10:
«сними флаги для этих писем»):
* site_mismatch, если домен сайта = домен почты адресата (сайт точно их);
* recent_contact, если прошлый контакт старше 30 дней (правило повтора 30 дней).
Остальные флаги не трогаем. Старый panel_json — в _ops/snyat-stop-flagi.jsonl.
Без --snyat — только счёт."""
import io
import json
import re
import sqlite3
import sys
import time
from datetime import date

c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
сн = "--snyat" in sys.argv


def дом(s):
    return re.sub(r"^www\.", "", str(s or "").lower().split("//")[-1].split("/")[0])


итог, ост, изм = {"site_mismatch": 0, "recent_contact": 0}, {}, []
for rid, email, pj in c.execute(
        "SELECT id, email, panel_json FROM confirm_reviews WHERE status='pending'").fetchall():
    p = json.loads(pj or "{}")
    if not (p.get("actions") or {}).get("confirm_hold"):
        continue
    co = p.get("company") or {}
    сайт = дом(co.get("site") or co.get("website"))
    флаги, оставить = p.get("stop_flags") or [], []
    for f in флаги:
        k = f.get("code") if isinstance(f, dict) else ""
        # --vse-site: владелец 16.10 «все контакты собраны с сайтов самих
        # компаний» — site_mismatch снимаем у всех.
        if k == "site_mismatch" and ("--vse-site" in sys.argv
                                     or (сайт and сайт == str(email or "").lower().split("@")[-1])):
            итог[k] += 1
            continue
        if k == "recent_contact":
            m = re.search(r"(\d{4}-\d{2}-\d{2})", f.get("label") or "")
            if m and (date.today() - date.fromisoformat(m.group(1))).days > 30:
                итог[k] += 1
                continue
        оставить.append(f)
        ост[k or "?"] = ост.get(k or "?", 0) + 1
    if len(оставить) != len(флаги):
        изм.append((rid, pj, оставить, p))
print("снимаю:", итог, "| карточек освобождается полностью:",
      sum(1 for x in изм if not x[2]), "| остаются флаги:", ост)
if сн:
    with io.open(r"C:\sender\_ops\snyat-stop-flagi.jsonl", "a", encoding="utf-8") as ж, c:
        for rid, pj, оставить, p in изм:
            ж.write(json.dumps({"id": rid, "panel_json": pj,
                                "ts": time.strftime("%Y-%m-%dT%H:%M:%S")},
                               ensure_ascii=False) + "\n")
            p["stop_flags"] = оставить
            a = dict(p.get("actions") or {})
            a["confirm_hold"] = bool(оставить)
            p["actions"] = a
            c.execute("UPDATE confirm_reviews SET panel_json=? WHERE id=? AND status='pending'",
                      (json.dumps(p, ensure_ascii=False), rid))
    print("снято, карточек изменено:", len(изм))
