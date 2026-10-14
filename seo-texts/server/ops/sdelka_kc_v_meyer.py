# -*- coding: utf-8 -*-
"""Владелец 14.10: «68 со сделкой КЦ в работе — вот этих верни для мейера».
Компании «Россия 9000»/«Белорусь 1000» с вердиктом «кц» и активной сделкой КЦ:
сделка КЦ Meyer не запрещает, поэтому открываем их Meyer —
  * enrich.db companies.verdikt_napr «кц» -> «оба» (источник «владелец 14.10»),
    иначе отбор генерации Meyer их не берёт;
  * obzvon-index.db obzvon.division += «+meyer», иначе панель не подберёт ящик
    Meyer (письмо Meyer шлём только с Meyer, а компании — только по метке).
Журнал — _ops/sdelka-kc-v-meyer.jsonl (fsync).

    sdelka_kc_v_meyer.py            — показать
    sdelka_kc_v_meyer.py primenit   — применить
"""
import io
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.sdelki_napr import blok  # noqa: E402

ПРИМ = "primenit" in sys.argv
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
o = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60)
группа = {}
for inn, ex in c.execute("SELECT inn, extra_json FROM recipients WHERE inn IS NOT NULL"):
    for г in ("Россия 9000", "Белорусь 1000"):
        if г in str(ex or "") and str(inn) not in группа:
            группа[str(inn)] = г
вердикт = {str(r[0]): (r[1] or "", r[2]) for r in e.execute("SELECT inn, verdikt_napr, name FROM companies")}
отвечали = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM leads WHERE inn IS NOT NULL")}
т = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
жур = io.open(r"C:\sender\_ops\sdelka-kc-v-meyer.jsonl", "a", encoding="utf-8")
n = {"всего": 0, "вердикт": 0, "метка": 0, "Meyer-сделка": 0}
for inn, г in группа.items():
    napr, имя = вердикт.get(inn, ("", None))
    if napr not in ("кц", "оба") or not blok(c, inn, "kc") or inn in отвечали:
        continue
    n["всего"] += 1
    if blok(c, inn, "meyer"):
        n["Meyer-сделка"] += 1      # есть и сделка Meyer — Meyer писать нельзя
        continue
    м = o.execute("SELECT division FROM obzvon WHERE inn=?", (inn,)).fetchone()
    print("%s | %s | %s | вердикт %s | метка %s" % (г, inn, (имя or "")[:40], napr, м and м[0]))
    if not ПРИМ:
        continue
    if napr == "кц":
        with e:
            e.execute("UPDATE companies SET verdikt_napr='оба', verdikt_istochnik='владелец 14.10' WHERE inn=?", (inn,))
        n["вердикт"] += 1
    if м is not None and "meyer" not in (м[0] or ""):
        нов = "+".join(x for x in [(м[0] or "").strip("+"), "meyer"] if x)
        with o:
            o.execute("UPDATE obzvon SET division=? WHERE inn=?", (нов, inn))
        n["метка"] += 1
    жур.write(json.dumps({"ts": т, "inn": inn, "было_вердикт": napr, "было_метка": м and м[0]}, ensure_ascii=False) + "\n")
жур.flush()
os.fsync(жур.fileno())
print(n)
print("=== СДЕЛКА КЦ -> MEYER: %s ===" % ("ПРИМЕНЕНО" if ПРИМ else "ПОКАЗ"))
