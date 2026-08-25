# -*- coding: utf-8 -*-
"""Письма блока КЦ легли в СНЯТЫЕ карточки. Текст в них свежий или старый?

Если свежий — деньги потрачены, а письмо невидимо: карточку надо оживить.
Если старый — генератор просто не смог записать, и оживлять нечего.
Смотрим время правки письма и первые строки тела.
"""
import io
import os
import re
import sqlite3

ЛОГ = r"C:\sender\_ops\ochered2508-blok2b-kc.log"
ид = []
for с in io.open(ЛОГ, encoding="utf-8", errors="replace"):
    м = re.search(r"#(\d+)\s*$", с.strip())
    if м:
        ид.append(int(м.group(1)))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
показано = 0
for н in sorted(set(ид)):
    р = c.execute(
        "SELECT cr.id, cr.status cs, cr.reason, m.id mid, m.status ms, "
        "       substr(m.updated_at,1,16) обн, substr(m.created_at,1,16) созд, "
        "       m.subject, substr(m.body_rendered,1,110) тело, r.company_name "
        "  FROM confirm_reviews cr "
        "  LEFT JOIN messages m ON m.id=cr.message_id "
        "  LEFT JOIN recipients r ON r.id=cr.recipient_id WHERE cr.id=?",
        (н,)).fetchone()
    if not р or р["cs"] != "skipped":
        continue
    показано += 1
    print("\n=== карточка #%s (%s) — %s" % (р["id"], р["cs"],
                                            str(р["company_name"] or "")[:34]))
    print("   причина снятия: %s" % str(р["reason"] or "")[:80])
    print("   письмо #%s %s | создано %s, правлено %s"
          % (р["mid"], р["ms"], р["созд"], р["обн"]))
    print("   тема: %s" % str(р["subject"] or "")[:70])
    print("   тело: %s" % " ".join(str(р["тело"] or "").split())[:100])
    if показано >= 5:
        break
