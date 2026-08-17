# -*- coding: utf-8 -*-
"""Сверка «сделано» против «в панели»: куда делась разница.

Вопрос соседней сессии 17.08: журнал говорит 159 писем, в кампаниях 10 и 11
их 134. Разница 25 не объяснена, а на необъяснённые числа опираться нельзя,
планируя добор.

Проходим по журналу ОДИН раз и раскладываем каждую запись с ок=true по
судьбе её review_id. Ничего не меняем.
"""
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

записи = [json.loads(s) for s in io.open(ЖУРНАЛ, encoding="utf-8")
          if s.strip()]
ок = [z for z in записи if z.get("ок")]
print(f"строк журнала: {len(записи)} | с ок=true: {len(ок)}")

# С 17.08 на письмо пишется ДВЕ строки (сгенерировано + итог). Считаем по
# получателям, иначе одно письмо посчитается дважды.
по_инн = {}
for z in ок:
    ключ = str(z.get("inn") or z.get("recipient_id"))
    по_инн.setdefault(ключ, []).append(z)
print(f"уникальных компаний с письмом: {len(по_инн)}")
дубли = sum(len(v) - 1 for v in по_инн.values() if len(v) > 1)
print(f"повторных строк по одной компании: {дубли}")

судьба = Counter()
без_review = []
for ключ, ряд in по_инн.items():
    rev = next((z.get("review_id") for z in reversed(ряд)
                if z.get("review_id")), None)
    if not rev:
        судьба["БЕЗ review_id (в панель не легло)"] += 1
        без_review.append(ряд[-1])
        continue
    row = store.confirm_get(int(rev))
    if not row:
        судьба["review_id есть, строки в базе НЕТ"] += 1
        continue
    ст = str(row.get("status") or "?")
    камп = int(row.get("campaign_id") or 0)
    судьба[f"{ст} (кампания {камп})"] += 1

print("\nсудьба каждого письма:")
for k, n in судьба.most_common():
    print(f"  {n:>4}  {k}")

print("\nбез review_id (первые 10):")
for z in без_review[:10]:
    print(f"  {str(z.get('имя'))[:34]:<36} брак: {str(z.get('брак'))[:60]}")

# Контрольный срез самой панели
for ст in ("pending", "approved", "sent", "skipped"):
    ряд = store.confirm_list(status=ст, limit=100000) or []
    свои = Counter(int(r.get("campaign_id") or 0) for r in ряд
                   if int(r.get("campaign_id") or 0) in (10, 11))
    if свои:
        print(f"панель, {ст}: {dict(свои)}")
