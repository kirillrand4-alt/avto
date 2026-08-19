# -*- coding: utf-8 -*-
"""Снять мейеровские письма производителям напитков.

Слово владельца 19.08: «напитки не надо». Правило уже стоит в генерации,
но письма, написанные до него, лежат в очереди. Берём pending и approved:
подтверждённое гасим самим письмом, решение не перерешивается.

Без аргумента - сухой прогон.
"""
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender import ai_letter as AI                               # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\snyatye-napitki.jsonl"
КАТИТЬ = "--катить" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    ряды = store._conn.execute(
        """SELECT c.id, c.status, COALESCE(rc.company_name,''),
                  COALESCE(rc.okved,''), COALESCE(rc.extra_json,'')
             FROM confirm_reviews c
             LEFT JOIN recipients rc ON rc.id=c.recipient_id
            WHERE c.campaign_id IN (7,8,9,11)
              AND c.status IN ('pending','approved')""").fetchall()

к_снятию, счёт = [], Counter()
for rid, st, фирма, оквэд, ex in ряды:
    деят = ""
    try:
        деят = str((json.loads(ex or "{}") or {}).get("activity") or "")
    except Exception:                                            # noqa: BLE001
        pass
    причина = AI.vne_profilya_meyer(оквэд, деят)
    if причина and "напитки" in причина:
        к_снятию.append((rid, фирма, st, причина))
        счёт[st] += 1

print(f"проверено писем: {len(ряды)}")
print(f"напитки в очереди: {len(к_снятию)} — {dict(счёт)}")
for rid, фирма, st, _ in к_снятию[:20]:
    print(f"  #{rid:<6} {str(фирма)[:44]:<46} {st}")
if not к_снятию or not КАТИТЬ:
    print("\nсухой прогон. Снять — аргумент --катить" if к_снятию
          else "снимать нечего")
    raise SystemExit(0)

снято = сбоев = 0
for rid, фирма, st, причина in к_снятию:
    try:
        ок = store.confirm_decide(
            rid, status="skipped",
            reason=f"не то направление: {причина[:200]}",
            decided_by="правило напитков (владелец 19.08)")
        if ок is False:
            карточка = store.confirm_get(rid) or {}
            mid = карточка.get("message_id")
            if mid:
                store.mark_skipped(int(mid), "напитки: не наш профиль Meyer")
        снято += 1
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": rid, "фирма": фирма, "было": st},
                               ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception as ex_:                                     # noqa: BLE001
        сбоев += 1
        if сбоев <= 5:
            print(f"  #{rid}: {type(ex_).__name__} {str(ex_)[:100]}")
print(f"\nснято: {снято} | сбоев: {сбоев}")
