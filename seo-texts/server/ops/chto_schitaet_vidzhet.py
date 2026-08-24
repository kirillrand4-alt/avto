# -*- coding: utf-8 -*-
"""Что за число «ждут подтверждения» в виджете ёмкости пулов.

Владелец видит в виджете 98, в списке очереди 10, а карточек со статусом
pending в базе четыре. Три разных числа — значит считаются три разные
вещи, и надо назвать какие, а не гадать.

Кандидаты: карточки confirm_reviews.pending (решение оператора) и письма
messages.pending_review (ручная очередь отправки). Это разные стадии
одного письма, и путать их нельзя: карточку оператор одобряет, письмо из
ручной очереди он отправляет.
"""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("=== КАРТОЧКИ ПОДТВЕРЖДЕНИЯ (confirm_reviews) ===")
for р in c.execute("SELECT status, COUNT(*) n FROM confirm_reviews "
                   "GROUP BY status ORDER BY n DESC"):
    print("  %-16s %d" % (р["status"], р["n"]))

print("\n=== ПИСЬМА В ОЧЕРЕДИ СООБЩЕНИЙ (messages) ===")
for р in c.execute("SELECT status, COUNT(*) n FROM messages "
                   "GROUP BY status ORDER BY n DESC"):
    print("  %-16s %d" % (р["status"], р["n"]))

print("\n=== ПИСЬМА СО СРОКОМ: СЕГОДНЯ И ПРОСРОЧЕННЫЕ ===")
for имя, усл in (
        ("ожидают отправки (scheduled+sending)",
         "status IN ('scheduled','sending')"),
        ("из них срок сегодня",
         "status IN ('scheduled','sending') "
         "AND substr(scheduled_at,1,10)=date('now')"),
        ("из них срок уже прошёл",
         "status IN ('scheduled','sending') AND scheduled_at < datetime('now')"),
        ("ручная очередь (pending_review)", "status='pending_review'")):
    print("  %-38s %d"
          % (имя, c.execute("SELECT COUNT(*) FROM messages WHERE %s"
                            % усл).fetchone()[0]))

print("\n=== ПРОСРОЧЕННЫЕ: КТО И ПОЧЕМУ ===")
for р in c.execute(
        "SELECT id, status, mailbox_id, scheduled_at, attempt_count, last_error "
        "  FROM messages WHERE status IN ('scheduled','sending') "
        "   AND scheduled_at < datetime('now') "
        " ORDER BY scheduled_at LIMIT 10"):
    print("  #%-6s %-10s %-34s срок %s | попыток %s"
          % (р["id"], р["status"], str(р["mailbox_id"] or "?")[:34],
             str(р["scheduled_at"])[:16], р["attempt_count"]))
    if р["last_error"]:
        print("      %s" % str(р["last_error"])[:110])

print("\n=== ЯЩИКИ НА ПАУЗЕ ===")
табл = {р[0] for р in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")}
if "mailbox_state" in табл:
    кол = [с[1] for с in c.execute("PRAGMA table_info(mailbox_state)")]
    поля = [п for п in ("mailbox_id", "paused", "paused_until", "reason",
                        "daily_limit", "sent_today", "ramp_day") if п in кол]
    print("  колонки: %s" % ", ".join(кол))
    for р in c.execute("SELECT %s FROM mailbox_state ORDER BY mailbox_id"
                       % ", ".join(поля)):
        строка = " | ".join("%s=%s" % (п, str(р[п])[:26]) for п in поля
                            if р[п] not in (None, "", 0))
        if "paused" in строка or "reason" in строка:
            print("  " + строка)
else:
    print("  таблицы mailbox_state нет")
