# -*- coding: utf-8 -*-
"""Показать отправленные письма Meyer целиком — как они на самом деле выглядят."""
import sqlite3

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=120)
s.row_factory = sqlite3.Row
ряды = [dict(r) for r in s.execute(
    "SELECT cr.subject, cr.body, cr.inn, r.company_name, r.email "
    "  FROM confirm_reviews cr "
    "  LEFT JOIN recipients r ON r.id = cr.recipient_id "
    "  JOIN send_log sl ON sl.message_id = cr.message_id "
    " WHERE cr.campaign_id=11 AND sl.outcome='sent' "
    " ORDER BY cr.id DESC LIMIT 5")]
s.close()

for i, р in enumerate(ряды, 1):
    print("=" * 78)
    print("ПИСЬМО %d | %s | %s" % (i, str(р.get("company_name"))[:44],
                                   str(р.get("email"))[:30]))
    print("ТЕМА: %s" % р.get("subject"))
    print("-" * 78)
    print(str(р.get("body") or "").strip())
    print("")
