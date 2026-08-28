# -*- coding: utf-8 -*-
"""Попадал ли основной домен в САМИ ПИСЬМА — отправленные и стоящие в очереди."""
import re
import sqlite3
from collections import Counter
БАЗА = r"C:\sender\sender.db"
ИСКАТЬ = ("prokompressor", "meyer-corp", "vsefotoseparatory", "usort.ru",
          "parsercompressor")
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row

def посчитать(запрос, подпись, параметры=()):
    всего = 0
    попались = Counter()
    примеры = []
    for r in c.execute(запрос, параметры):
        тело = " ".join(str(r["t"] or "").split())
        всего += 1
        for сл in ИСКАТЬ:
            if сл in тело.lower():
                попались[сл] += 1
                if len(примеры) < 4:
                    i = тело.lower().index(сл)
                    примеры.append("…%s…" % тело[max(0, i - 70):i + 50])
    print("%s: писем %d, с нашими доменами в тексте %d"
          % (подпись, всего, sum(попались.values())))
    if попались:
        print("   по доменам: %s" % dict(попались))
        for п in примеры:
            print("   %s" % п)

посчитать("SELECT COALESCE(body_rendered,'') t FROM messages "
          " WHERE sent_at IS NOT NULL AND COALESCE(body_rendered,'') <> ''",
          "ОТПРАВЛЕННЫЕ (тело в messages)")
посчитать("SELECT COALESCE(cr.edited_body, cr.body, '') t FROM confirm_reviews cr "
          " WHERE cr.status IN ('sent','approved')",
          "РЕШЕНИЯ ОПЕРАТОРА (отправленные и одобренные)")
посчитать("SELECT COALESCE(cr.edited_body, cr.body, '') t FROM confirm_reviews cr "
          " WHERE cr.status='pending_review'",
          "СТОЯТ В ОЧЕРЕДИ НА ПОДТВЕРЖДЕНИЕ")
посчитать("SELECT COALESCE(m.body_rendered,'') t FROM messages m "
          " WHERE m.status IN ('scheduled','pending_review') "
          "   AND COALESCE(m.body_rendered,'') <> ''",
          "СТОЯТ В ОЧЕРЕДИ НА ОТПРАВКУ")
print()
print("=== подписи: что стоит в конце писем ===")
хвосты = Counter()
for r in c.execute("SELECT COALESCE(cr.edited_body, cr.body, '') t "
                   "  FROM confirm_reviews cr WHERE cr.status IN ('sent','approved') "
                   " LIMIT 400"):
    строки = [с.strip() for с in str(r["t"] or "").split("\n") if с.strip()]
    if строки:
        хвосты[" | ".join(строки[-3:])[:110]] += 1
for х, n in хвосты.most_common(6):
    print("   %3d  %s" % (n, х))
c.close()
