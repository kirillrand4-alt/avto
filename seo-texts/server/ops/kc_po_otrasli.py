# -*- coding: utf-8 -*-
"""Решения «кц» предклассификатора по одной отрасли книги: компания, причина, паспорт.

    kc_po_otrasli.py "Зерно" [napr=кц]
"""
import io
import json
import sqlite3
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
арг = [а for а in sys.argv[1:] if "=" not in а]
им = dict(а.split("=", 1) for а in sys.argv[1:] if "=" in а)
ОТР = арг[0] if арг else "Зерно"
НАПР = им.get("napr", "кц")
реш = {}
for с in io.open(r"C:\sender\_ops\predklass-vsey-bazy.jsonl", encoding="utf-8"):
    д = json.loads(с)
    реш[д["inn"]] = д
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
сег, имя = {}, {}
for inn, s, n in c.execute("SELECT inn, segment, company_name FROM recipients WHERE inn IS NOT NULL"):
    сег[str(inn)] = s or ""
    имя[str(inn)] = n
import os
import re
os.environ.setdefault("PROVIDER_THINKING_FIELD", "omit")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.ai_quota import build_ai_quota  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
q = build_ai_quota(Store(cfg.get("service.db_path", r"C:\sender\sender.db")), cfg)
ТИХО = "tiho" in им
СЛОВА = [w for w in им.get("slova", "").split(",") if w]
спис = [д for i, д in реш.items() if д.get("napr") == НАПР and ОТР.lower() in сег.get(i, "").lower()]
print("%s в «%s»: %d" % (НАПР, ОТР, len(спис)))
print("ключи записи:", sorted(спис[0].keys()) if спис else "-")
сч = Counter()
for д in спис:
    i = д["inn"]
    f = q._site_facts(i) or {}
    пасп = "; ".join("%s: %s" % (кл, (v if isinstance(v, str) else ", ".join(map(str, v)))[:150])
                     for кл, v in f.items() if v and кл in ("продукция", "сырьё", "оборудование_линии"))
    for w in СЛОВА:
        if re.search(w, пасп, re.I):
            сч[w] += 1
    if not пасп:
        сч["(без паспорта)"] += 1
    ФИЛЬТР = им.get("filtr")
    if ФИЛЬТР and not re.search(ФИЛЬТР, пасп, re.I):
        continue
    сч["показано"] += 1
    if сч["показано"] > int(им.get("do", "9999")):
        continue
    if not ТИХО:
        print("- %s | %s" % (str(имя.get(i))[:40], пасп.replace("\n", " ")[:230] or "(паспорта нет)"))
print("слова:", dict(сч))
