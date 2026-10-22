# -*- coding: utf-8 -*-
"""Сверка FSA-MEYER-v4 (КЦ и Meyer) с нашей базой (владелец 22.10: «насколько
полезен для письма»). Вход — fsa-v4-inns.json с дропа: {kc|meyer: {ИНН: [ярус,
выручка, почта_конвейера]}}. По ярусам: уже писали (любое направление / это
направление), письмо в работе, лид, есть в получателях, новые. Только чтение."""
import io
import json
import os
import sqlite3
from collections import Counter, defaultdict

import requests

У = os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/")
д = requests.get(У + "/fsa-v4-inns.json", headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=120).json()
c = sqlite3.connect(r"C:\sender\sender.db")
кам = {r[0]: (r[1] or "") for r in c.execute("SELECT id, name FROM campaigns")}
напр = lambda cid: "meyer" if "meyer" in кам.get(cid, "").lower() or "мейер" in кам.get(cid, "").lower() else "kc"
писали = defaultdict(set)
for inn, cid in c.execute("SELECT DISTINCT inn, campaign_id FROM send_log WHERE outcome='sent' AND inn IS NOT NULL"):
    писали[str(inn)].add(напр(cid))
вработе = {str(r[0]) for r in c.execute("SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                                        "WHERE m.status NOT IN ('sent','skipped','failed') AND r.inn IS NOT NULL")}
лиды = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM leads WHERE inn IS NOT NULL")}
получ = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM recipients WHERE inn IS NOT NULL")}
for тег, инны in д.items():
    сч = defaultdict(Counter)
    for inn, (ярус, vr, _) in инны.items():
        if inn in лиды:
            к = "лид (уже отвечали)"
        elif тег in писали.get(inn, ()):
            к = "уже писали этим направлением"
        elif inn in вработе:
            к = "письмо в работе"
        elif писали.get(inn):
            к = "писали другим направлением"
        elif inn in получ:
            к = "есть в получателях, не писали"
        else:
            к = "новые (нет в панели)"
        сч[к][ярус] += 1
        сч[к]["всего"] += 1
    print("=====", тег, len(инны))
    for к, v in сч.items():
        print("  %-34s %s" % (к, dict(sorted(v.items()))))


# Новые (нет в панели, не писали, не лид) — список ИНН на дроп для заливки
# (владелец 22.10: «Ярус А 1319 мейер запускай»).
новые = {тег: [inn for inn in инны if inn not in лиды and inn not in получ and not писали.get(inn) and inn not in вработе]
         for тег, инны in д.items()}
r = requests.put(У + "/fsa-v4-novye.json", data=json.dumps(новые).encode(),
                 headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=120)
print("новые на дроп:", {k: len(v) for k, v in новые.items()}, r.status_code)
