# -*- coding: utf-8 -*-
"""Доложить в очередь письма, которые есть в журнале, но не попали в панель.

Страховка к тому, что текст письма теперь пишется в журнал ДО постановки в
очередь. Если база была занята и запись не прошла, письмо всё равно цело -
берём его отсюда и кладём, не платя модели второй раз.

Сухой прогон; писать - argv[1] == "primenit".
"""
import io
import json
import os
import sys
from collections import Counter
from datetime import date

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                     # noqa: E402
from sender.config import Config                               # noqa: E402
from sender.confirm import ConfirmSend                         # noqa: E402
from sender.store import Store                                 # noqa: E402
from sender.suppression import Suppression                     # noqa: E402

ПРИМЕНИТЬ = len(sys.argv) > 1 and sys.argv[1] == "primenit"
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
КАМПАНИЯ = {"kc": 10, "meyer": 11}

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))

есть_текст, счёт = [], Counter()
for s in (io.open(ЖУРНАЛ, encoding="utf-8") if os.path.exists(ЖУРНАЛ) else []):
    try:
        z = json.loads(s)
    except Exception:
        continue
    if not z.get("тело"):
        счёт["без текста в журнале"] += 1
        continue
    rid_rev = z.get("review_id")
    if rid_rev and (store.confirm_get(int(rid_rev)) or {}).get("body"):
        счёт["уже в очереди"] += 1
        continue
    есть_текст.append(z)

print(f"записей с текстом, но без строки очереди: {len(есть_текст)}")
for k, n in счёт.most_common():
    print(f"  {k:<28} {n}")

if not ПРИМЕНИТЬ or not есть_текст:
    print("сухой прогон: ничего не менял" if not ПРИМЕНИТЬ else "докладывать нечего")
    raise SystemExit(0)

день = date.today().isoformat()
положено = 0
for z in есть_текст:
    rid = int(z["recipient_id"])
    rec = store.get_recipient(rid)
    if not rec:
        continue
    div = str(z.get("направление") or "kc")
    cid = КАМПАНИЯ.get(div, 10)
    mid, _st, почему = q._ensure_message(cid, rid)
    if not mid:
        print(f"  #{rid}: нет message_id ({почему})")
        continue
    try:
        req = q._request(rec)
        req["target_division"] = div
        panel = q._panel(rec, {"subject": z["тема"], "body": z["тело"]},
                         день, req)
    except Exception:                                          # noqa: BLE001
        panel = {}
    r = cs.submit(email=str(getattr(rec, "email", "") or ""),
                  subject=z["тема"], body=z["тело"],
                  inn=str(z.get("inn") or "") or None,
                  campaign_id=cid, recipient_id=rid, message_id=mid,
                  panel=panel)
    положено += 1 if str(getattr(r, "status", "")) == "pending" else 0
    print(f"  #{rid} {str(z.get('имя'))[:30]:<32} -> "
          f"{getattr(r, 'status', '?')} #{getattr(r, 'review_id', '?')}")
print(f"\nдоложено в очередь: {положено} из {len(есть_текст)}")
