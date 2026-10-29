# -*- coding: utf-8 -*-
"""Снять письма, построенные на чужом сайте (проверка chuzhoy_sayt_inn.py, 29.10).
Список согласован владельцем: 15 из группы «почти наверняка чужой»,
Хлебпищепром (7724305352) оставлен по его слову.
    snyat_chuzhoy_sayt.py [--primenit]"""
import sqlite3
import sys
from datetime import datetime

ИНН = ["2623028657", "1828024235", "4705092512", "6144022895", "6725034840",
       "6950057285", "7716257867", "7727458149", "7733450927",
       "7743197141", "7811787254", "7816729810", "2205012699", "7105041688"]
ПРИЧИНА = "чужой сайт (дистрибьютор/другая фирма) — снято владельцем 29.10"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
т = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
ряды = c.execute(
    "SELECT c.id, c.status cst, c.message_id, c.email, r.inn, r.company_name, m.status mst "
    "FROM confirm_reviews c LEFT JOIN recipients r ON r.id=c.recipient_id "
    "LEFT JOIN messages m ON m.id=c.message_id "
    "WHERE r.inn IN (%s) AND ((c.status='pending') OR (c.status IN ('approved','edited') "
    "AND m.status IN ('scheduled','pending_review')))" % ",".join("?" * len(ИНН)), ИНН).fetchall()
к = п = 0
for р in ряды:
    print("  #%s %s/%s %s %s %s" % (р["id"], р["cst"], р["mst"], р["inn"], р["company_name"][:40], р["email"]))
    if "--primenit" in sys.argv:
        with c:
            if р["message_id"]:
                п += c.execute("UPDATE messages SET status='skipped', last_error=? WHERE id=? "
                               "AND status IN ('pending_review','scheduled')", (ПРИЧИНА, р["message_id"])).rowcount
            к += c.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_at=?, updated_at=? "
                           "WHERE id=? AND status IN ('pending','approved','edited')", (ПРИЧИНА, т, т, р["id"])).rowcount
print("найдено %d | снято карточек %d, писем %d%s" % (len(ряды), к, п, "" if "--primenit" in sys.argv else " (СУХОЙ ПРОГОН)"))
