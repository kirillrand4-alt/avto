# -*- coding: utf-8 -*-
"""Кто в очереди сейчас рискует уйти с ящика чужого направления.

Считаем ровно так, как будет считать починенный гейт: поле
panel.letter_division, а если его нет - товарная лексика письма. Показываем
письма, у которых поля НЕТ (значит до правки гейт по ним молчал), и что о
них говорит лексика.
"""
import json
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
try:
    from sender.napravlenie_pisma import po_leksike                # noqa: E402
except Exception:                                                  # noqa: BLE001
    МАРКЕРЫ = {
        "kc": ("компрессор", "азот", "кислород", " мкс", "пневмо", "воздуходув"),
        "meyer": ("рентген", "фотосепар", "фото-сепар", "инспекц", "сортировк"),
    }

    def po_leksike(текст):
        т = str(текст or "").lower()
        п = {k for k, ms in МАРКЕРЫ.items() if any(m in т for m in ms)}
        return next(iter(п)) if len(п) == 1 else None

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT cr.id, cr.status, cr.campaign_id, cr.email, cr.subject, "
    "       COALESCE(cr.panel_json,'') pj, COALESCE(cr.body,'') body, "
    "       m.id mid, m.status mst, r.company_name "
    "  FROM confirm_reviews cr "
    "  LEFT JOIN messages m ON m.id=cr.message_id "
    "  LEFT JOIN recipients r ON r.id=cr.recipient_id "
    " WHERE m.status IN ('scheduled','pending_review','queued') "
    "    OR cr.status='pending'"
).fetchall()
print(f"писем в работе (не отправлены): {len(ряды)}")

счёт = Counter(); без_поля = []
for р in ряды:
    try:
        п = json.loads(р["pj"] or "{}")
    except Exception:                                              # noqa: BLE001
        п = {}
    поле = str(п.get("letter_division") or "").strip().lower()
    лекс = po_leksike(f"{р['subject']} {р['body']}")
    камп = int(р["campaign_id"] or 0)
    счёт[f"поле={поле or 'НЕТ'} лексика={лекс or '-'}"] += 1
    if поле not in ("kc", "meyer"):
        без_поля.append((р["id"], р["mid"], р["mst"], р["status"], камп,
                         лекс, р["email"], р["company_name"], р["subject"]))

print("\nраскладка (поле генератора / лексика письма):")
for к, н in счёт.most_common():
    print(f"  {н:>4}  {к}")
print(f"\nБЕЗ ПОЛЯ НАПРАВЛЕНИЯ: {len(без_поля)} - до правки гейт по ним молчал")
по_камп = Counter(f"камп{б[4]} лексика={б[5] or '-'}" for б in без_поля)
for к, н in по_камп.most_common():
    print(f"  {н:>4}  {к}")
print("\nпервые 15:")
for б in без_поля[:15]:
    print(f"  #{б[0]} письмо={б[1]} {б[2] or '-'}/{б[3]} камп{б[4]} "
          f"лексика={б[5] or '-'} {б[6]}")
    print(f"       {str(б[7])[:30]} | {str(б[8])[:60]}")
