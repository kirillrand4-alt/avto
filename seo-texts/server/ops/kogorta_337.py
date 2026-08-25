# -*- coding: utf-8 -*-
"""Та самая партия из 337: ищем по подписи возврата, а не по причине.

Причину карточки могли переписать более поздние заслоны, а decided_by
возврата — своя метка. Заодно смотрим, кто вообще переписывал причины.
"""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
for условие, подпись in (
        ("cr.decided_by LIKE '%возврат подтверждения%'", "по подписи возврата"),
        ("cr.reason LIKE '%устаревшему правилу 2%'", "ещё висит на правиле 2")):
    ряды = c.execute(
        "SELECT cr.status st, COALESCE(m.status,'нет письма') ms, "
        "       substr(COALESCE(m.sent_at,''),1,10) д, cr.reason rs "
        "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
        " WHERE " + условие).fetchall()
    print("=== %s: %d ===" % (подпись, len(ряды)))
    for к, н in Counter("карта %s / письмо %s" % (р["st"], р["ms"])
                        for р in ряды).most_common(6):
        print("   %-40s %5d" % (к, н))
    дни = Counter(р["д"] for р in ряды if р["ms"] == "sent")
    for к, н in дни.most_common():
        print("   отправлены %s: %d" % (к, н))
    прич = Counter((р["rs"] or "")[:44] for р in ряды)
    for к, н in прич.most_common(5):
        print("   причина сейчас: %-46s %5d" % (к, н))
    print()

print("=== ВСЕ ПРИЧИНЫ КАРТОЧЕК, РЕШЁННЫХ 25.08 ===")
for р in c.execute(
        "SELECT COALESCE(decided_by,'-') кто, COUNT(*) n FROM confirm_reviews "
        " WHERE substr(decided_at,1,10)='2026-08-25' GROUP BY кто "
        " ORDER BY n DESC LIMIT 10"):
    print("   %-52s %5d" % (р["кто"][:52], р["n"]))
