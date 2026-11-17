# -*- coding: utf-8 -*-
"""Вернуть карточку 52952 (снята по ошибке 17.11 вместе с ручными правками: тот же адрес, другое письмо) в pending."""
import sqlite3, time
т = time.strftime("%Y-%m-%dT%H:%M:%S"); c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
with c:
    mid = c.execute("SELECT message_id FROM confirm_reviews WHERE id=52952 AND reason LIKE 'снято владельцем 17.11%'").fetchone()
    if mid:
        c.execute("UPDATE confirm_reviews SET status='pending', reason=NULL, decided_at=NULL, updated_at=? WHERE id=52952", (т,))
        c.execute("UPDATE messages SET status='pending_review', last_error=NULL, updated_at=? WHERE id=? AND status='skipped'", (т, mid[0]))
print(c.execute("SELECT id, status, email, subject FROM confirm_reviews WHERE id=52952").fetchone())
