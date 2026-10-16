# -*- coding: utf-8 -*-
"""Часовой пояс получателей живых писем: есть tz или падает на окно (Москва);
у скольких без tz пояс выводится из региона ИНН. Плюс настройка окна. Только чтение."""
import sqlite3, sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.config import Config
cfg = Config.load(r"C:\sender\sender.yaml")
for k in ("auto_send.window", "auto_send", "send_window"):
    try: print(k, "=", cfg.get(k, None))
    except Exception as e: print(k, e)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кол = [r[1] for r in c.execute("PRAGMA table_info(recipients)")]
print("tz в recipients:", "tz" in кол)
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
сч, пояса = Counter(), Counter()
for cid, st, tz, inn in c.execute("SELECT m.campaign_id, m.status, r.tz, r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                                  "WHERE m.status IN ('pending_review','approved','scheduled') AND m.campaign_id IN (14,16)"):
    k = кам.get(cid)
    if tz: сч[(k, "tz есть")] += 1; пояса[tz] += 1
    else:
        inn = str(inn or "")
        сч[(k, "без tz, ИНН с регионом" if len(inn) in (10, 12) else "без tz, ИНН нет")] += 1
for k, v in sorted(сч.items()): print(v, k)
print("пояса:", пояса.most_common(12))
