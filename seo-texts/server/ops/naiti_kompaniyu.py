# -*- coding: utf-8 -*-
"""Найти компанию по телефону / куску адреса / ролику в письмах ящика."""
import sqlite3
import sys
тел, кусок, ящик, ролик = sys.argv[1], sys.argv[2].lower(), sys.argv[3], sys.argv[4]
цифры = "".join(ч for ч in тел if ч.isdigit())[-10:]
cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
for inn, name, ph in cx.execute("SELECT inn, name, phones FROM companies WHERE replace(replace(replace(replace(coalesce(phones,''),' ',''),'-',''),'(',''),')','') LIKE ?",
                                ("%" + цифры + "%",)):
    print("enrich телефон: %s %s" % (inn, name))
for inn, e in cx.execute("SELECT inn, email FROM emails WHERE lower(email) LIKE ?", ("%" + кусок + "%",)):
    print("enrich почта: %s %s" % (inn, e))
try:
    ox = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=30)
    кол = [р[1] for р in ox.execute("PRAGMA table_info(obzvon)")]
    print("колонки обзвона: %s" % кол[:40])
    имя_к = next((к for к in кол if "name" in к.lower() or "назв" in к.lower()), кол[0])
    поля = [к for к in кол if any(с in к.lower() for с in ("тел", "phone", "почт", "mail"))]
    for к in поля:
        for р in ox.execute("SELECT inn, %s FROM obzvon WHERE replace(replace(replace(coalesce(%s,''),' ',''),'-',''),'(','') LIKE ? LIMIT 5" % (имя_к, к),
                            ("%" + (цифры if "тел" in к.lower() or "phone" in к.lower() else кусок) + "%",)):
            print("обзвон (%s): %s" % (к, tuple(р)))
except Exception as е:  # noqa: BLE001
    print("обзвон: %s" % str(е)[:100])
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
n = 0
for р in c.execute("SELECT m.id, r.company_name, r.inn, r.email, m.sent_at FROM messages m JOIN recipients r ON r.id=m.recipient_id "
                   "WHERE m.mailbox_id=? AND m.status='sent' AND m.body_rendered LIKE ? ORDER BY m.sent_at DESC", (ящик, "%" + ролик + "%")):
    n += 1
    if n <= 15:
        print("письмо %s с роликом: m%s %s ИНН %s <%s> %s" % (ящик, р[0], р[1], р[2], р[3], str(р[4])[:16]))
print("всего писем ящика с роликом: %d" % n)
print("=== НАЙТИ КОМПАНИЮ ===")
