# -*- coding: utf-8 -*-
"""По каким доменам оставшиеся непроверенные — не упёрлись ли в темп на домен."""
import sqlite3
from collections import Counter

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
дом = Counter()
for r in c.execute(
        "SELECT DISTINCT lower(trim(cr.email)) e FROM confirm_reviews cr"
        " LEFT JOIN addr_probe p ON p.email = lower(trim(cr.email))"
        " WHERE cr.campaign_id=11 AND cr.created_at >= '2026-08-31'"
        "   AND p.email IS NULL"):
    дом[r[0].rsplit("@", 1)[-1]] += 1
print("=== НЕПРОВЕРЕННЫЕ ПО ДОМЕНАМ ===")
for д, n in дом.most_common(14):
    print("   %-28s %4d" % (д, n))
print("   доменов всего: %d, адресов: %d" % (len(дом), sum(дом.values())))

дом2 = Counter()
for r in c.execute(
        "SELECT DISTINCT lower(trim(cr.email)) e FROM confirm_reviews cr"
        " JOIN addr_probe p ON p.email = lower(trim(cr.email))"
        " WHERE cr.campaign_id=11 AND cr.created_at >= '2026-08-31'"
        "   AND p.source='проба'"):
    дом2[r[0].rsplit("@", 1)[-1]] += 1
print("\n=== УЖЕ ПРОВЕРЕННЫЕ ПО ДОМЕНАМ (топ) ===")
for д, n in дом2.most_common(8):
    print("   %-28s %4d" % (д, n))
c.close()

публичные = ("mail.ru", "yandex.ru", "bk.ru", "inbox.ru", "list.ru", "ya.ru",
             "gmail.com", "rambler.ru", "internet.ru")
пуб = sum(n for д, n in дом.items() if д in публичные)
print("\n=== ИТОГ ===")
print("непроверенных: %d, из них на публичных почтовиках: %d (%.0f%%)"
      % (sum(дом.values()), пуб,
         100.0 * пуб / sum(дом.values()) if дом else 0))
print("если почти все на паре доменов — работник упёрся в свой темп на домен,")
print("и это защита, а не поломка: ломиться быстрее нельзя.")
