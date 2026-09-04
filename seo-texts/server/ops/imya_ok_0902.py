# -*- coding: utf-8 -*-
"""Только чтение: что значит imya_ok и сколько исходников про вебинар."""
import sqlite3

e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== imya_ok ===")
for р in e.execute("SELECT imya_ok, COUNT(*) n FROM emails GROUP BY imya_ok"
                   " ORDER BY n DESC LIMIT 6"):
    print("  %-10s %d" % (str(р["imya_ok"]), р["n"]))
print("  примеры с imya_ok:")
for р in e.execute("SELECT email, person, imya_ok FROM emails"
                   " WHERE person<>'' AND imya_ok IS NOT NULL LIMIT 5"):
    print("    %-32s %-28s imya_ok=%s" % (р["email"][:32], str(р["person"])[:28],
                                          р["imya_ok"]))

print("\n=== СКОЛЬКО РЕШЕНИЙ ПРО ВЕБИНАР ===")
n = s.execute("SELECT COUNT(*) FROM confirm_reviews WHERE body LIKE '%вебинар%'"
              " OR subject LIKE '%вебинар%'").fetchone()[0]
print("  решений со словом «вебинар»: %d" % n)
for р in s.execute("SELECT campaign_id, COUNT(*) k FROM confirm_reviews"
                   " WHERE body LIKE '%вебинар%' GROUP BY campaign_id"):
    print("    кампания %-4s %d" % (р["campaign_id"], р["k"]))

print("\n=== ДРУГИЕ ПРИВЯЗКИ КО ВРЕМЕНИ В ПИСЬМАХ ===")
for слово in ("вебинар", "августа", "сентября", "на следующей неделе", "завтра",
              "прошедш", "приглаша"):
    k = s.execute("SELECT COUNT(*) FROM confirm_reviews WHERE body LIKE ?",
                  ("%" + слово + "%",)).fetchone()[0]
    print("  «%-20s» %d" % (слово, k))
