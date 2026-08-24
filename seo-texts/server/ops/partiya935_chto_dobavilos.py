# -*- coding: utf-8 -*-
"""Партия 935: сколько компаний, что добавилось и сколько из них без письма.

Владелец: «там должны были добавиться компании». Смотрим по датам заведения
получателей, а не по общему счётчику: важно не сколько всего, а что пришло
свежего и готово ли оно к работе.
"""
import json
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

сегменты = Counter(str(р["segment"] or "(пусто)") for р in
                   c.execute("SELECT segment FROM recipients"))
print("получатели по сегментам:")
for с, н in сегменты.most_common(12):
    print(f"  {н:>6}  {с}")

ряды = c.execute(
    "SELECT r.id, r.email, r.company_name, r.inn, r.segment, "
    "       substr(r.created_at,1,10) заведён, "
    "       COALESCE(r.extra_json,'') extra, "
    "       (SELECT COUNT(*) FROM confirm_reviews cr WHERE cr.recipient_id=r.id) писем, "
    "       (SELECT COUNT(*) FROM messages m WHERE m.recipient_id=r.id "
    "          AND m.status='sent') ушло "
    "  FROM recipients r").fetchall()
партия = [р for р in ряды
          if "935" in str(р["segment"] or "")
          or "935" in str(р["extra"] or "")]
print(f"\nв Партии 935 (по сегменту или по группе): {len(партия)}")

print("\nкогда заводились:")
for д, н in sorted(Counter(str(р["заведён"]) for р in партия).items())[-12:]:
    print(f"  {н:>6}  {д}")

без_письма = [р for р in партия if int(р["писем"] or 0) == 0]
неотправленные = [р for р in партия
                  if int(р["писем"] or 0) > 0 and int(р["ушло"] or 0) == 0]
print(f"\nбез единого письма:        {len(без_письма)}")
print(f"письмо есть, но не ушло:   {len(неотправленные)}")
print(f"уже написано и отправлено: {len(партия) - len(без_письма) - len(неотправленные)}")

if без_письма:
    свежие = sorted(без_письма, key=lambda р: str(р["заведён"]), reverse=True)
    print("\nсамые свежие без письма:")
    for р in свежие[:12]:
        гр = ""
        try:
            гр = ",".join(json.loads(р["extra"] or "{}").get("gruppy") or [])
        except Exception:                                          # noqa: BLE001
            pass
        print(f"  {р['заведён']} {str(р['company_name'])[:34]:<34} "
              f"{str(р['email'])[:30]:<30} ИНН {р['inn'] or '-'} {гр}")
