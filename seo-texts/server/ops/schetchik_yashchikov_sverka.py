# -*- coding: utf-8 -*-
"""Счётчик ящика против фактических писем за сегодня.

mailbox_state.sent_today у мейеровских показывает 20 при лимите 5, а
фактически сегодня ушло меньше. Прежде чем решать про лимиты, надо знать,
врёт счётчик или нет: от этого зависит, есть ли у ящиков запас.
"""
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.store import Store                                      # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

факт = Counter(str(р["mailbox_id"]) for р in c.execute(
    "SELECT mailbox_id FROM messages WHERE status='sent' "
    "AND substr(COALESCE(sent_at,updated_at),1,10)='2026-08-21'"))
лог = Counter()
try:
    лог = Counter(str(р["mailbox_id"]) for р in c.execute(
        "SELECT mailbox_id FROM send_log WHERE substr(ts,1,10)='2026-08-21'"))
except Exception as ex:                                            # noqa: BLE001
    print(f"send_log: {str(ex)[:70]}")
    колонки = [р[1] for р in c.execute("PRAGMA table_info(send_log)")]
    print("колонки send_log:", ", ".join(колонки))

print(f"{'ящик':<44} {'счётчик':>8} {'messages':>9} {'send_log':>9}")
для_пула = Counter()
for mb in cfg.mailboxes():
    ст = store.get_mailbox_state(mb.mailbox_id)
    сч = getattr(ст, "sent_today", 0) if ст else 0
    print(f"{mb.mailbox_id:<44} {сч:>8} {факт.get(mb.mailbox_id,0):>9} "
          f"{лог.get(mb.mailbox_id,0):>9}")
    для_пула[str(mb.division)] += сч
print(f"\nсумма счётчиков по направлениям: {dict(для_пула)}")
print(f"фактически ушло сегодня (messages): {sum(факт.values())}")
