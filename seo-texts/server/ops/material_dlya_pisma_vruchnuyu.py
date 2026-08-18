# -*- coding: utf-8 -*-
"""Материал, чтобы написать письмо руками: сайт, прежнее письмо, контакты."""
import json
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ИНН = [a for a in sys.argv[1:] if a.isdigit() and len(a) >= 9]
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
con = sqlite3.connect(r"file:C:\sender\enrich.db?mode=ro", uri=True, timeout=10)

for inn in ИНН:
    print("=" * 72)
    r = con.execute("SELECT url, text FROM site_text WHERE inn=?",
                    (inn,)).fetchone()
    f = con.execute("SELECT facts_json FROM site_facts WHERE inn=?",
                    (inn,)).fetchone()
    c = con.execute("SELECT name, activity, region FROM companies WHERE inn=?",
                    (inn,)).fetchone()
    print(f"ИНН {inn}  {c[0] if c else ''}")
    print(f"  деятельность: {c[1] if c else ''}")
    print(f"  сайт: {r[0] if r else '(нет)'}")
    if f and f[0]:
        try:
            п = json.loads(f[0])
            for k in ("продукция", "оборудование_линии", "мощности",
                      "контроль_качества", "масштаб"):
                if п.get(k):
                    print(f"  {k}: {str(п[k])[:220]}")
        except Exception:                                        # noqa: BLE001
            pass
    print(f"\n  --- ТЕКСТ САЙТА (1800 знаков):")
    print("  " + re.sub(r"\n", "\n  ", ((r[1] if r else "") or "")[:1800]))
    with store._lock:
        ряд = store._conn.execute(
            "SELECT id, email, subject, body, status FROM confirm_reviews "
            "WHERE inn=? ORDER BY id DESC LIMIT 1", (inn,)).fetchall()
    for cid, email, тема, тело, ст in ряд:
        print(f"\n  --- ПРЕЖНЕЕ ПИСЬМО #{cid} ({ст}) на {email}")
        print(f"  ТЕМА: {тема}")
        print("  " + re.sub(r"<[^>]+>", " ", тело or "")[:900].replace("\n", "\n  "))
con.close()
