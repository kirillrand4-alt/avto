# -*- coding: utf-8 -*-
"""Где письма блока КЦ: номер в логе — это ПИСЬМО, а не карточка.

Первая попытка читала «#5416» как номер карточки и вышла ерунда: те
карточки заведены 17.08 и сняты, тело у них пустое — значит генератор в
них ничего не писал. Ищем те же номера в messages.

Новых карточек прогон завёл 415, а блок КЦ отчитался о 445 письмах —
значит он писал в УЖЕ существующие карточки. Смотрим их состояние поимённо,
а не по агрегату: важно, лежат они в ожидании, подтверждены или сняты.
"""
import io
import os
import re
import sqlite3
from collections import Counter

ЛОГИ = [r"C:\sender\_ops\ochered2508-blok2b-kc.log",
        r"C:\sender\_ops\ochered2508-blok2c-kc.log"]
ид = []
for п in ЛОГИ:
    if not os.path.exists(п):
        continue
    for с in io.open(п, encoding="utf-8", errors="replace"):
        м = re.search(r"#(\d+)\s*$", с.strip())
        if м:
            ид.append(int(м.group(1)))
print("номеров карточек в логах блока КЦ: %d (уникальных %d)"
      % (len(ид), len(set(ид))))
if ид:
    print("   диапазон: #%d … #%d" % (min(ид), max(ид)))

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
состояния = Counter()
примеры = []
for н in sorted(set(ид)):
    р = c.execute(
        "SELECT m.id, m.status ms, substr(m.created_at,1,16) созд, "
        "       COALESCE(cr.status,'нет карточки') cs, cr.id cid, "
        "       cr.decided_by, r.company_name FROM messages m "
        "  LEFT JOIN confirm_reviews cr ON cr.message_id=m.id "
        "  LEFT JOIN recipients r ON r.id=m.recipient_id WHERE m.id=?",
        (н,)).fetchone()
    if not р:
        состояния["письма нет в базе"] += 1
        continue
    состояния["письмо %s / карта %s" % (р["ms"], р["cs"])] += 1
    if len(примеры) < 8:
        примеры.append(р)
print("\n=== СОСТОЯНИЕ ЭТИХ КАРТОЧЕК ===")
for к, н in состояния.most_common():
    print("   %-44s %5d" % (к, н))
print("\n=== ПРИМЕРЫ ===")
for р in примеры:
    print("   письмо #%-6s %-14s создано %s | карточка %s (%s) | %s"
          % (р["id"], р["ms"], р["созд"], р["cid"] or "-", р["cs"],
             str(р["company_name"] or "")[:28]))
