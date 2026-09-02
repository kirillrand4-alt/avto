# -*- coding: utf-8 -*-
"""Только чтение: письмо Ирины с её ящика и, для проверки, с чужого."""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config      # noqa: E402
from sender.store import Store        # noqa: E402
import sender.sender as SS            # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
камп = store.get_campaign(12)
snd = SS.Sender.__new__(SS.Sender)
snd.config = cfg
snd.store = store
RM = SS.RenderedMessage

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
р = c.execute("SELECT subject, body FROM confirm_reviews WHERE campaign_id=12"
              " AND body LIKE '%Ирина Кузнецова%' ORDER BY id LIMIT 1").fetchone()

for ящик, кто in (("i.kuznetsova@sort-systems.ru", "ЕЁ ящик"),
                  ("a.tyunin@sort-systems.ru", "ЧУЖОЙ ящик (Артем Тюнин)")):
    итог = snd._apply_signature(RM(subject=р["subject"], body=р["body"]), ящик, камп)
    т = итог.body
    print("=== %s: %s ===" % (кто, ящик))
    строки = [л for л in т.splitlines() if л.strip()]
    print("  вступление: %s" % строки[1][:150])
    print("  женские формы в тексте: %s"
          % ("есть" if ("была" in т or "решила" in т or "Хотела" in т) else "НЕТ"))
    print("  хвост:")
    for л in т.splitlines()[-5:]:
        print("    " + л)
    print()
