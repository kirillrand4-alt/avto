# -*- coding: utf-8 -*-
"""Сходятся ли направления у сегодняшних писем.

Ищем расхождение: метка компании говорит одно, письмо ушло по другому.
Плюс смотрим, чем обосновано направление - досчитано цепочкой или взято
готовым полем (explicit). Массовый explicit + перекос в kc = вернулся
старый баг с подстановкой направления по умолчанию.
"""
import json
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
строки = c.execute(
    "SELECT cr.id, cr.campaign_id, cr.email, cr.subject, "
    "       COALESCE(cr.panel_json,'') AS pj "
    "  FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id "
    " WHERE m.status='sent' AND substr(m.updated_at,1,10)='2026-08-21'"
).fetchall()
print(f"отправлено сегодня: {len(строки)}")
почему = Counter(); напр = Counter(); расхождения = []
for р in строки:
    try:
        п = json.loads(р["pj"] or "{}")
    except Exception:                                             # noqa: BLE001
        п = {}
    L = п.get("letter") or {}
    д = str(L.get("division") or п.get("letter_division") or "")
    пч = str(L.get("division_reason") or п.get("letter_division_reason") or "")
    метка = str(((п.get("company") or {}).get("division")) or "")
    камп = "kc" if int(р["campaign_id"] or 0) in (9, 10) else "meyer"
    почему[пч or "нет"] += 1
    напр[f"{д or '?'} -> камп {камп}"] += 1
    if д and камп and д != камп:
        расхождения.append((р["id"], р["email"], д, камп, метка, р["subject"]))
    elif метка and д and метка != д and "+" not in метка:
        расхождения.append((р["id"], р["email"], д, камп, метка, р["subject"]))
print("\nобоснование направления:", dict(почему))
print("направление письма -> кампания:", dict(напр))
print(f"\nрасхождений: {len(расхождения)}")
for r in расхождения[:10]:
    print(f"  №{r[0]} {r[1]}: письмо={r[2]} кампания={r[3]} метка={r[4]}")
    print(f"       {r[5][:70]}")
