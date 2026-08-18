# -*- coding: utf-8 -*-
"""Сколько в партии медицины и что с их письмами уже произошло.

Владелец увидел в списке офтальмологическую клинику и спросил: «зачем нам
такая компания то?». Прежде чем резать класс, надо знать объём: сколько их
в очереди, скольким уже ушло письмо и во что это обошлось.

Медицину берём по ОКВЭД 86-88 (здравоохранение и соцуслуги) и по слову в
названии - код часто формален, а клиника в названии видна сразу.
"""
import io
import json
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

РЕЦ = r"C:\sender\_ops\rezenzii-pisem.jsonl"
СЛОВА = ("клиник", "медцентр", "медицинск", "стоматолог", "офтальм",
         "хирург", "диагностик", "поликлиник", "больниц", "госпитал",
         "лечебн", "здоровь", "мед ")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

верд = {}
for s in io.open(РЕЦ, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
        верд[int(z["id"])] = str(z.get("verdict") or "")
    except Exception:                                            # noqa: BLE001
        pass

with store._lock:
    ряды = store._conn.execute(
        """SELECT c.id, c.status, COALESCE(rc.okved,''),
                  COALESCE(rc.company_name,''), COALESCE(m.status,'')
             FROM confirm_reviews c
             LEFT JOIN recipients rc ON rc.id=c.recipient_id
             LEFT JOIN messages m ON m.id=c.message_id
            WHERE c.campaign_id IN (10,11)""").fetchall()

по_статусу = Counter()
по_вердикту = Counter()
письма = Counter()
имена_ушедших = []
всего_мед = 0
for rid, st, ок, имя, mst in ряды:
    код = re.sub(r"[^0-9.]", "", str(ок))[:2]
    по_названию = any(с in str(имя).lower() for с in СЛОВА)
    if код not in ("86", "87", "88") and not по_названию:
        continue
    всего_мед += 1
    по_статусу[st] += 1
    по_вердикту[верд.get(rid) or "не рецензировано"] += 1
    письма[mst or "нет письма"] += 1
    if mst == "sent":
        имена_ушедших.append(имя[:44])

print(f"медицинских получателей с письмом в кампаниях 10-11: {всего_мед}")
print("\nрешение оператора:")
for k, n in по_статусу.most_common():
    print(f"  {n:>5}  {k}")
print("\nвердикт рецензента:")
for k, n in по_вердикту.most_common():
    print(f"  {n:>5}  {k}")
print("\nсостояние письма:")
for k, n in письма.most_common():
    print(f"  {n:>5}  {k}")
print(f"\nуже отправлено {len(имена_ушедших)}, первые 15:")
for и in имена_ушедших[:15]:
    print(f"  {и}")
