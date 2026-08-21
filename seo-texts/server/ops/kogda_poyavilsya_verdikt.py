# -*- coding: utf-8 -*-
"""Вердикт «нет ящика» появился ДО письма или ИЗ отбивки?

От этого зависит вся причинно-следственная связь. Вердикт старше письма -
слали на заведомо мёртвый адрес, виноват молчащий заслон. Вердикт моложе
письма и источник «отбивка» - её же и породила, заслон ни при чём, а
настоящую причину роста надо искать в другом.
"""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
адреса = ["director@nitek-nn.ru", "sales@morpro.ru", "operato@food-pro.net",
          "sale@pmilk.ru", "zakaz@esagro.ru", "140941@rambler.ru",
          "os@snemaservis.ru"]
for а in адреса:
    п = c.execute("SELECT * FROM addr_probe WHERE lower(email)=?",
                  (а.lower(),)).fetchone()
    м = c.execute(
        "SELECT m.id, m.status, substr(COALESCE(m.sent_at,m.updated_at),1,19) когда "
        "  FROM messages m LEFT JOIN recipients r ON r.id=m.recipient_id "
        " WHERE lower(COALESCE(r.email,''))=? ORDER BY m.id DESC LIMIT 1",
        (а.lower(),)).fetchone()
    print(f"\n{а}")
    if п:
        d = dict(п)
        print(f"   проба: вердикт={d.get('verdict')} источник={d.get('source')} "
              f"время={d.get('ts')} код={d.get('code')}")
        print(f"   ответ сервера: {str(d.get('answer') or '')[:110]}")
    else:
        print("   пробы нет вовсе")
    if м:
        print(f"   письмо {м['id']} ({м['status']}) отправлено {м['когда']}")

print("\n=== источники вердиктов в кэше целиком ===")
for р in c.execute("SELECT source, verdict, COUNT(*) n FROM addr_probe "
                   "GROUP BY source, verdict ORDER BY n DESC LIMIT 14"):
    print(f"  {р['n']:>6}  источник={str(р['source'])[:22]:<22} {р['verdict']}")
