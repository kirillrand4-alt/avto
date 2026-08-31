# -*- coding: utf-8 -*-
"""Стоит ли ждать пробу по mail.ru и yandex: что она вообще там говорит."""
import sqlite3
from collections import Counter, defaultdict

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
c.row_factory = sqlite3.Row

print("=== ПАРТИЯ: ВЕРДИКТ ПО ДОМЕНАМ (только то, что проверил работник) ===")
свод = defaultdict(Counter)
for r in c.execute(
        "SELECT lower(trim(cr.email)) e, p.verdict в FROM confirm_reviews cr"
        "  JOIN addr_probe p ON p.email = lower(trim(cr.email))"
        " WHERE cr.campaign_id=11 AND cr.created_at >= '2026-08-31'"
        "   AND p.source='проба'"):
    свод[r["e"].rsplit("@", 1)[-1]][r["в"]] += 1
for д in sorted(свод, key=lambda x: -sum(свод[x].values()))[:8]:
    всего = sum(свод[д].values())
    части = ", ".join("%s %d" % (в, n) for в, n in свод[д].most_common())
    print("   %-16s всего %3d: %s" % (д, всего, части))

print("\n=== ТО ЖЕ ПО ВСЕЙ БАЗЕ ПРОБ (насколько проба полезна на домене) ===")
свод2 = defaultdict(Counter)
for r in c.execute("SELECT email, verdict FROM addr_probe WHERE source='проба'"):
    д = str(r["email"] or "").rsplit("@", 1)[-1]
    if д in ("mail.ru", "yandex.ru", "gmail.com", "bk.ru", "inbox.ru",
             "list.ru", "rambler.ru"):
        свод2[д][r["verdict"]] += 1
for д in sorted(свод2, key=lambda x: -sum(свод2[x].values())):
    всего = sum(свод2[д].values())
    ящика_нет = свод2[д].get("нет ящика", 0)
    print("   %-14s всего %5d: %s   → «нет ящика» %.1f%%"
          % (д, всего,
             ", ".join("%s %d" % (в, n) for в, n in свод2[д].most_common(4)),
             100.0 * ящика_нет / всего if всего else 0))
c.close()

print("\n=== ИТОГ ===")
print("если на mail.ru и yandex почти всё «принимает всё» — ожидание этих")
print("135 адресов почти ничего не даёт: домен не выдаёт несуществующий ящик.")
