# -*- coding: utf-8 -*-
"""Падения писем партии по КЛАССАМ ошибок, а не по уникальному тексту."""
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server\ops")
from sender.store import Store                                  # noqa: E402
import varianty_pisma as V                                      # noqa: E402

КЛАССЫ = (
    ("пароль ящика не подошёл (535 auth failed)", ("auth failed", "5.7.8", "535")),
    ("отказ по спаму (554 5.7.1)", ("suspicion of SPAM", "5.7.1")),
    ("адреса нет (550)", ("550", "No such user", "unknown user")),
    ("лимит/частота (451/452/421)", ("451", "452", "421", "too many")),
    ("соединение/таймаут", ("timed out", "Connection", "10060", "10061")),
)


def класс(т):
    н = (т or "").lower()
    for имя, ключи in КЛАССЫ:
        if any(k.lower() in н for k in ключи):
            return имя
    return "прочее: " + (т or "нет текста")[:60]


store = Store(r"C:\sender\sender.db")
с = Counter()
пары = Counter()
когда = Counter()
with store._lock:
    for р in store._conn.execute(
            """SELECT m.last_error, m.mailbox_id, m.updated_at
                 FROM confirm_reviews c JOIN messages m ON c.message_id = m.id
                WHERE c.subject IN (%s) AND m.status='failed'"""
            % ",".join("?" * len(V.ТЕМЫ)), tuple(V.ТЕМЫ)):
        к = класс(str(р["last_error"] or ""))
        с[к] += 1
        пары[(str(р["mailbox_id"] or "?"), к)] += 1
        когда[str(р["updated_at"] or "")[:13] + " | " + к] += 1
print("--- по ящику и классу ---")
for (я, к), в in пары.most_common(8):
    print("   %-40s %-42s %5d" % (я[:40], к[:42], в))
print("")
print("--- по часам ---")
for к in sorted(когда)[-8:]:
    print("   %-64s %5d" % (к[:64], когда[к]))
print("")
print("=" * 74)
print("=== КЛАССЫ ПАДЕНИЙ (партия) ===")
for к, в in с.most_common(8):
    print("   %-52s %5d" % (к[:52], в))
print("всего failed: %d" % sum(с.values()))
