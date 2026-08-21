# -*- coding: utf-8 -*-
"""Когда на самом деле сделаны письма без поля направления.

Я назвал 142 карточки кампании 1 «старыми новостными», не посмотрев на
даты. Владелец: «там же не может быть старых, скорее всего это новые
генерированные сегодня». Смотрим факт: дата создания карточки, дата письма
и имя кампании - по каждой группе.
"""
import json
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
имена = {int(р["id"]): str(р["name"] or "")
         for р in c.execute("SELECT id, name FROM campaigns")}
ряды = c.execute(
    "SELECT cr.id, cr.campaign_id, cr.status, cr.created_at, cr.subject, "
    "       COALESCE(cr.panel_json,'') pj, "
    "       m.id mid, m.status mst, substr(m.created_at,1,10) mdate "
    "  FROM confirm_reviews cr "
    "  LEFT JOIN messages m ON m.id=cr.message_id "
    " WHERE m.status IN ('scheduled','pending_review','queued') "
    "    OR cr.status='pending'"
).fetchall()

без = []
for р in ряды:
    try:
        п = json.loads(р["pj"] or "{}")
    except Exception:                                              # noqa: BLE001
        п = {}
    if str(п.get("letter_division") or "").strip().lower() in ("kc", "meyer"):
        continue
    без.append(р)
print(f"писем в работе без поля направления: {len(без)}")

по_камп = Counter(f"камп{р['campaign_id']} «{имена.get(int(р['campaign_id'] or 0),'?')[:26]}»"
                  for р in без)
print("\nпо кампаниям:")
for к, н in по_камп.most_common():
    print(f"  {н:>4}  {к}")

print("\nпо дате создания карточки:")
for к, н in sorted(Counter(str(р["created_at"])[:10] for р in без).items()):
    print(f"  {н:>4}  {к}")

print("\nкампания x дата создания:")
for к, н in sorted(Counter(
        f"камп{р['campaign_id']} {str(р['created_at'])[:10]}" for р in без).items()):
    print(f"  {н:>4}  {к}")

print("\nстатусы карточек:", dict(Counter(str(р["status"]) for р in без)))
print("статусы писем:", dict(Counter(str(р["mst"]) for р in без)))
print("\nсамые свежие пять:")
for р in sorted(без, key=lambda x: str(x["created_at"]))[-5:]:
    print(f"  #{р['id']} камп{р['campaign_id']} создана {р['created_at'][:16]} "
          f"письмо {р['mid']} ({р['mst']}) | {str(р['subject'])[:52]}")
