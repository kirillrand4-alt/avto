# -*- coding: utf-8 -*-
"""Почему Meyer не уходит: статусы писем Meyer, last_error свежих, что в 'sending'."""
import sqlite3
from collections import Counter
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
мк = [k for k, v in кам.items() if "meyer" in str(v).lower() or "мейер" in str(v).lower()]
q = ",".join("?" * len(мк))
print("статусы Meyer:", Counter(r[0] for r in c.execute("SELECT status FROM messages WHERE campaign_id IN (%s)" % q, мк)).most_common(12))
print("sending всего:", c.execute("SELECT COUNT(*), MIN(updated_at) FROM messages WHERE status='sending'").fetchone())
print("\nпоследние изменения Meyer (updated_at):")
for r in c.execute("SELECT id, status, scheduled_at, updated_at, substr(coalesce(last_error,''),1,110), mailbox_id FROM messages "
                   "WHERE campaign_id IN (%s) ORDER BY updated_at DESC LIMIT 15" % q, мк):
    print("  ", r)
print("\nошибки Meyer за сегодня:", Counter((r[0] or "")[:70] for r in c.execute(
    "SELECT last_error FROM messages WHERE campaign_id IN (%s) AND updated_at >= date('now') AND last_error IS NOT NULL" % q, мк)).most_common(10))
print("\nближайшие одобренные Meyer по scheduled_at:")
for r in c.execute("SELECT id, status, scheduled_at, mailbox_id FROM messages WHERE campaign_id IN (%s) AND status IN ('scheduled','approved') "
                   "ORDER BY scheduled_at LIMIT 8" % q, мк):
    print("  ", r)
print("\nстатусы КЦ-1:", Counter(r[0] for r in c.execute("SELECT m.status FROM messages m JOIN campaigns k ON k.id=m.campaign_id WHERE k.name LIKE 'КЦ-1%'")).most_common(8))
