# -*- coding: utf-8 -*-
"""Откуда в письме факт: карточка, паспорт, ОКВЭД по адресу получателя + поиск слова."""
import json
import sqlite3
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.ai_quota import build_ai_quota  # noqa: E402
адрес, слово = sys.argv[1].lower(), sys.argv[2].lower()
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
c = sqlite3.connect(r"C:\sender\sender.db")
rid = c.execute("SELECT id FROM recipients WHERE lower(email)=?", (адрес,)).fetchone()[0]
req = q._request(store.get_recipient(rid))
print("компания: %s | ИНН %s | ОКВЭД %s | сегмент %s" % (req.get("company_name"), store.get_recipient(rid).inn, req.get("okved"), req.get("segment")))
print("activity: %s" % str(req.get("activity"))[:700])
ex = req.get("extra") or {}
sf = ex.get("site_facts") or {}
print("site_facts: %s" % json.dumps(sf, ensure_ascii=False)[:900])
for к, v in ex.items():
    if слово in json.dumps(v, ensure_ascii=False).lower():
        print("СЛОВО «%s» найдено в extra.%s: %s" % (слово, к, json.dumps(v, ensure_ascii=False)[:300]))
if слово in str(req.get("activity") or "").lower():
    print("СЛОВО «%s» найдено в activity" % слово)
print("=== ОТКУДА ФАКТ ===")
