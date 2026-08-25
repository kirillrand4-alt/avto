# -*- coding: utf-8 -*-
"""Пять последних писем блока КЦ: что реально лежит в их карточках.

Хватит гадать по агрегатам. Берём последние строки лога, читаем номер
review_id (его печатает сам генератор) и смотрим карточку с письмом
целиком: статус, время правки, тема и начало тела.
"""
import io
import re
import sqlite3

ЛОГ = r"C:\sender\_ops\ochered2508-blok2b-kc.log"
строки = [с.strip() for с in io.open(ЛОГ, encoding="utf-8", errors="replace")
          if re.search(r"#\d+\s*$", с.strip())]
print("строк с номером: %d, последние пять:" % len(строки))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
for с in строки[-5:]:
    н = int(re.search(r"#(\d+)\s*$", с).group(1))
    print("\n--- %s" % с[:110])
    р = c.execute(
        "SELECT cr.id, cr.status cs, substr(cr.created_at,1,16) зав, "
        "       substr(cr.updated_at,1,16) обн, cr.message_id, "
        "       r.company_name, r.email FROM confirm_reviews cr "
        "  LEFT JOIN recipients r ON r.id=cr.recipient_id WHERE cr.id=?",
        (н,)).fetchone()
    if not р:
        print("   карточки #%d НЕТ" % н)
        continue
    print("   карточка #%s %s | заведена %s | правлена %s | %s <%s>"
          % (р["id"], р["cs"], р["зав"], р["обн"],
             str(р["company_name"] or "")[:30], str(р["email"] or "")[:30]))
    if р["message_id"]:
        м = c.execute("SELECT id, status, substr(created_at,1,16) созд, "
                      "       substr(updated_at,1,16) обн, subject, "
                      "       substr(body_rendered,1,90) тело FROM messages "
                      " WHERE id=?", (р["message_id"],)).fetchone()
        if м:
            print("   письмо #%s %s | создано %s | правлено %s"
                  % (м["id"], м["status"], м["созд"], м["обн"]))
            print("   тема: %s" % str(м["subject"] or "(пусто)")[:70])
            print("   тело: %s" % " ".join(str(м["тело"] or "(пусто)").split())[:90])
    else:
        print("   письма у карточки нет")
