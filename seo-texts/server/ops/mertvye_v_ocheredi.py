# -*- coding: utf-8 -*-
"""Сколько писем в очереди нацелено на адреса с приговором пробы.

Заслон мёртвого адреса (confirm._nedostavimyy) стоит ТОЛЬКО на ручном пути.
auto_send._send_one проверяет окно, повтор и пустой текст - и всё; вердикт
пробы он не спрашивает вовсе. Поэтому приговор, пришедший ПОСЛЕ постановки
письма в очередь, письмо оттуда не убирает: оно уходит и отбивается.

Считаем, сколько таких писем стоит прямо сейчас - это и есть отбивки,
которые мы получим, если просто снять паузу.
"""
import sqlite3
from collections import Counter

ПРИГОВОР = ("нет ящика", "нет MX")

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
проба = {str(р["email"]).lower(): str(р["verdict"] or "")
         for р in c.execute("SELECT email, verdict FROM addr_probe")
         if р["email"]}

ряды = c.execute(
    "SELECT m.id mid, m.status mst, m.campaign_id, cr.id rid, cr.status cst, "
    "       COALESCE(cr.email, r.email) email, r.company_name "
    "  FROM messages m "
    "  LEFT JOIN confirm_reviews cr ON cr.message_id=m.id "
    "  LEFT JOIN recipients r ON r.id=m.recipient_id "
    " WHERE m.status IN ('scheduled','queued','pending_review')"
).fetchall()
print(f"писем в очереди: {len(ряды)}")

счёт = Counter(); мёртвые = []
for р in ряды:
    в = проба.get(str(р["email"] or "").lower(), "нет вердикта")
    счёт[в] += 1
    if в in ПРИГОВОР:
        мёртвые.append((р["mid"], р["mst"], р["campaign_id"], р["email"],
                        р["company_name"], в))
print("\nвердикт пробы у писем в очереди:")
for в, н in счёт.most_common():
    метка = "  <-- ПРИГОВОР" if в in ПРИГОВОР else ""
    print(f"  {н:>4}  {в}{метка}")

print(f"\nписем на мёртвые адреса: {len(мёртвые)}")
for м in мёртвые[:20]:
    print(f"  письмо {м[0]} ({м[1]}) камп{м[2]} {м[3]} — {str(м[4])[:30]} [{м[5]}]")

# сколько таких уже УШЛО за всё время - цена молчащего заслона
ушли = c.execute(
    "SELECT COALESCE(cr.email, r.email) email "
    "  FROM messages m LEFT JOIN confirm_reviews cr ON cr.message_id=m.id "
    "  LEFT JOIN recipients r ON r.id=m.recipient_id "
    " WHERE m.status='sent'").fetchall()
мёртвых_ушло = sum(1 for р in ушли
                   if проба.get(str(р["email"] or "").lower(), "") in ПРИГОВОР)
print(f"\nуже отправлено на адреса с приговором: {мёртвых_ушло} из {len(ушли)}")
