# -*- coding: utf-8 -*-
"""Что было с отправкой с 21.08: сработал ли автостоп по отказам.

Правку выкатили 21-го, с тех пор прошло три дня. Смотрим по факту: сколько
уходило, сколько отказов, гасил ли рубеж ящики и в каком состоянии пулы
сейчас.
"""
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.store import Store                                      # noqa: E402

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ушло = Counter(str(р[0]) for р in c.execute(
    "SELECT substr(COALESCE(sent_at,updated_at),1,10) FROM messages "
    "WHERE status='sent' AND COALESCE(sent_at,updated_at) >= '2026-08-21'"))
отказ = Counter(str(р[0]) for р in c.execute(
    "SELECT substr(COALESCE(event_ts,created_at),1,10) FROM events "
    "WHERE event_type='reject_spam' AND COALESCE(event_ts,created_at) >= '2026-08-21'"))
print(f"{'день':<12} {'ушло':>7} {'отказов':>9} {'доля':>7}")
for д in sorted(set(ушло) | set(отказ)):
    у, о = ушло.get(д, 0), отказ.get(д, 0)
    print(f"{д:<12} {у:>7} {о:>9} {(100.0*о/(у+о) if (у+о) else 0):>6.1f}%")

print("\nотказы с ящиком (после правки ящик пишется):")
for р in c.execute(
        "SELECT mailbox_id, COUNT(*) n FROM events WHERE event_type='reject_spam' "
        "AND mailbox_id IS NOT NULL GROUP BY mailbox_id ORDER BY n DESC"):
    print(f"  {р['n']:>4}  {р['mailbox_id']}")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
сейчас = datetime.now(timezone.utc)
print(f"\nсейчас UTC {сейчас:%Y-%m-%d %H:%M}")
на_паузе = []
for mb in cfg.mailboxes():
    ст = store.get_mailbox_state(mb.mailbox_id)
    if ст is not None and getattr(ст, "paused", False):
        на_паузе.append((mb.mailbox_id, str(getattr(ст, "pause_reason", "") or "")))
print(f"ящиков на паузе: {len(на_паузе)} из {len(list(cfg.mailboxes()))}")
for я, п in на_паузе[:8]:
    print(f"  {я:<42} причина: {п[:60] or '(без причины)'}")

очередь = c.execute(
    "SELECT status, COUNT(*) n FROM messages WHERE status IN "
    "('scheduled','pending_review','queued') GROUP BY status").fetchall()
print("\nв очереди:", {р["status"]: р["n"] for р in очередь})
