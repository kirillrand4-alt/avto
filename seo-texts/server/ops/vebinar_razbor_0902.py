# -*- coding: utf-8 -*-
"""Только чтение: 1) слушается ли закреплённый ящик; 2) почему проходит
компрессорный ящик; 3) почему не на паузе food-sort."""
import inspect
import io
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.suppression import Suppression  # noqa: E402
import sender.sender as S                   # noqa: E402
import sender.gates as G                    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
snd = S.Sender(cfg, store, Suppression(store), G.Gates(cfg, store))
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

print("=== 3. ЯЩИКИ FOOD-SORT: СОСТОЯНИЕ ===")
for р in c.execute("SELECT * FROM mailbox_state WHERE mailbox_id LIKE '%food-sort%'"):
    print("  %-30s paused=%s причина=%s ramp=%s лимит=%s сег=%s"
          % (р["mailbox_id"], р["paused"], str(р["pause_reason"])[:30],
             р["ramp_day"], р["daily_limit"], р["sent_today"]))

print("\n=== 2. ГЕЙТ НАПРАВЛЕНИЙ НА НАШЕМ ПОЛУЧАТЕЛЕ ===")
р = c.execute("SELECT recipient_id FROM messages WHERE campaign_id=12"
              " AND (mailbox_id IS NULL OR mailbox_id='') LIMIT 1").fetchone()
rec = store.get_recipient(р["recipient_id"])
msg = None
мид = c.execute("SELECT id FROM messages WHERE recipient_id=? AND campaign_id=12",
                (р["recipient_id"],)).fetchone()
if мид:
    msg = store.get_message(мид["id"])
print("  получатель: %s segment=%s inn=%s okved=%s"
      % (rec.email, getattr(rec, "segment", None), getattr(rec, "inn", None),
         getattr(rec, "okved", None)))
for ящик in ("a.tyunin@sort-systems.ru", "a.balakirev@compressor-store.ru",
             "i.kuznetsova@sort-systems.ru", "a.erokhin@food-sort.ru"):
    try:
        б = snd.division_block(rec, ящик, message=msg)
    except Exception as ex:
        б = "ОШИБКА %s" % str(ex)[:60]
    print("    %-34s блок=%s" % (ящик, б))

print("\n=== 1. СЛУШАЕТСЯ ЛИ messages.mailbox_id ===")
т = io.open(r"C:\sender\sender\orchestrator.py", encoding="utf-8",
            errors="replace").read() if __import__("os").path.exists(
    r"C:\sender\sender\orchestrator.py") else ""
if т:
    лн = т.splitlines()
    for м in re.finditer(r"pick_mailbox|mailbox_id", т):
        н = т[:м.start()].count("\n")
        с = лн[н].strip()
        if с.startswith("#"):
            continue
        print("  orchestrator.py:%d  %s" % (н + 1, с[:100]))
else:
    print("  orchestrator.py не найден")
