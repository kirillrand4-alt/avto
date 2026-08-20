# -*- coding: utf-8 -*-
"""Почему у карточек-копий нет message_id и как панель их отправляет."""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
for rid in (2601, 3312, 3473):
    r = c.execute("SELECT * FROM confirm_reviews WHERE id=?", (rid,)).fetchone()
    if not r:
        continue
    д = dict(r)
    print(f"#{rid} kind={д.get('kind')!r} message_id={д.get('message_id')!r} "
          f"campaign={д.get('campaign_id')} recipient={д.get('recipient_id')} "
          f"in_reply_to={str(д.get('in_reply_to'))[:40]!r} "
          f"thread={str(д.get('thread_id'))[:30]!r} "
          f"manual_ts={д.get('manual_email_ts')!r}")

print("\n== сколько вообще карточек без письма ==")
for r in c.execute(
        "SELECT status, COUNT(*) n FROM confirm_reviews "
        "WHERE message_id IS NULL GROUP BY status ORDER BY n DESC"):
    print(f"  {r['status']:<12} {r['n']}")

print("\n== и сколько из них kind ==")
for r in c.execute(
        "SELECT COALESCE(kind,'(пусто)') k, COUNT(*) n FROM confirm_reviews "
        "WHERE message_id IS NULL GROUP BY k ORDER BY n DESC"):
    print(f"  {r['k']:<16} {r['n']}")
