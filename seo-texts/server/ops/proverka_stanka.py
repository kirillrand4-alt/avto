# -*- coding: utf-8 -*-
"""Карточка пластика: какой главный станок видит генератор."""
import sqlite3
import sys
sys.path.insert(0, r"C:\sender")
from sender import ai_letter as AL  # noqa: E402
from sender.ai_quota import build_ai_quota  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(r"C:\sender\sender.db")
q = build_ai_quota(store, cfg)
for отр in ("Пластик и полимеры", "Мясо, птица, молоко"):
    with store._lock:
        rid = store._conn.execute(
            "SELECT id FROM recipients WHERE segment=? AND extra_json LIKE "
            "'%Россия 9000%' LIMIT 1", (отр,)).fetchone()[0]
    req = q._request(store.get_recipient(rid))
    блок = AL._recipient_block(0, req, "meyer")
    стр = [с for с in блок.splitlines() if "ГЛАВНЫЙ СТАНОК" in с]
    print("%-22s -> %s" % (отр, (стр[0][:90] if стр else "строки нет")))
print("=== ПРОВЕРКА СТАНКА ===")
