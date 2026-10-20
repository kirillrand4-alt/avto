# -*- coding: utf-8 -*-
"""Проверка варианта 4: блок получателя августовского модуля для двух крупных
компаний КЦ-1 (чётный и нечётный ИНН) — есть ли вставка. Без вызова модели."""
import importlib.util
import io
import json
import sqlite3
import sys
sys.path.insert(0, r"C:\sender")
import sender  # noqa: E402
сп = importlib.util.spec_from_file_location("sender.ai_letter", r"C:\sender\server\ops\ai_letter_avgust.py")
A = importlib.util.module_from_spec(сп)
sys.modules["sender.ai_letter"] = A
сп.loader.exec_module(A)
sender.ai_letter = A
from sender.ai_quota import build_ai_quota  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
e = sqlite3.connect(r"C:\sender\enrich.db")
выр = {str(r[0]): r[1] for r in e.execute("SELECT inn, revenue_rub FROM companies WHERE revenue_rub>=5e8")}
нашли = {}
for rid in json.load(io.open(r"C:\sender\_ops\spisok-kc1.json")):
    rec = store.get_recipient(rid)
    inn = str(getattr(rec, "inn", "") or "")
    em = str(getattr(rec, "email", "") or "").strip().lower()
    if inn in выр and float(выр[inn] or 0) < 1e9 and sum(map(ord, em)) % 2 not in нашли:
        нашли[sum(map(ord, em)) % 2] = rec
    if len(нашли) == 2:
        break
for чёт, rec in sorted(нашли.items()):
    req = q._request(rec)
    print("ключи:", sorted(req), sorted((req.get("extra") or {}))[:40])
    print("==== ИНН", req.get("inn"), "чётный" if чёт == 0 else "нечётный", "| revenue в extra:", (req.get("extra") or {}).get("revenue"))
    блок = A._recipient_block(0, req, "kc")
    print([s for s in блок.splitlines() if "ФРАЗА О СЕБЕ" in s] or "вставки нет", "| ОКВЭД", req.get("okved"))
