# -*- coding: utf-8 -*-
"""Доложить в очередь письма, которые есть в журнале, но не попали в панель.

Страховка к тому, что текст письма пишется в журнал ДО постановки в
очередь. Если база была занята и запись не прошла, письмо всё равно цело -
берём его отсюда и кладём, не платя модели второй раз.

На письмо в журнале ДВЕ строки: «текст» (там тема и тело) и «итог» (там
review_id и статус очереди). Итоговой строки может не быть вовсе - это и
означает, что письмо до панели не доехало.

Сухой прогон; писать - argv[1] == "primenit".
"""
import io
import json
import os
import sys
import time
from collections import Counter
from datetime import date

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                     # noqa: E402
from sender.config import Config                               # noqa: E402
from sender.confirm import ConfirmSend                         # noqa: E402
from sender.store import Store                                 # noqa: E402
from sender.suppression import Suppression                      # noqa: E402

ПРИМЕНИТЬ = len(sys.argv) > 1 and sys.argv[1] == "primenit"
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
КАМПАНИЯ = {"kc": 10, "meyer": 11}

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))


def _с_ожиданием(зовём):
    """Повторить вызов, пока база занята. Возвращает (значение, сбой).

    Без этого одна блокировка роняла ВЕСЬ доклад: письма, дольше всех
    ждавшие очереди, теряли последний шанс в неё попасть.
    """
    посл = None
    for поп in range(6):
        try:
            return зовём(), None
        except Exception as ex:                                # noqa: BLE001
            посл = ex
            if "locked" not in str(ex).lower() and поп >= 2:
                break
            time.sleep(2 + поп * 3)
    return None, посл


тексты, размещено, видели = {}, {}, set()
for s in (io.open(ЖУРНАЛ, encoding="utf-8") if os.path.exists(ЖУРНАЛ) else []):
    try:
        z = json.loads(s)
    except Exception:                                          # noqa: BLE001
        continue
    rid = z.get("recipient_id")
    if rid is None:
        continue
    rid = int(rid)
    видели.add(rid)
    if z.get("тело"):
        тексты[rid] = z
    rev = z.get("review_id")
    if rev:
        размещено.setdefault(rid, set()).add(int(rev))

счёт = Counter()
счёт["без текста в журнале"] = len(видели) - len(тексты)
есть_текст = []
for rid in sorted(тексты):
    # УЖЕ В ОЧЕРЕДИ смотрим по карточке, а не по одному наличию review_id:
    # строку могли снять, и тогда письмо надо класть заново.
    if any((store.confirm_get(rev) or {}).get("body")
           for rev in размещено.get(rid, ())):
        счёт["уже в очереди"] += 1
        continue
    есть_текст.append(тексты[rid])

print(f"записей с текстом, но без строки очереди: {len(есть_текст)}")
for k, n in счёт.most_common():
    if n:
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
    пара, сбой = _с_ожиданием(lambda: q._ensure_message(cid, rid))
    mid = почему = None
    if пара is not None:
        mid, _st, почему = пара
    if not mid:
        print(f"  #{rid}: нет message_id ({почему or str(сбой)[:90]})")
        continue
    try:
        req = q._request(rec)
        req["target_division"] = div
        panel = q._panel(rec, {"subject": z["тема"], "body": z["тело"]},
                         день, req)
    except Exception:                                          # noqa: BLE001
        panel = {}
    r, сбой = _с_ожиданием(lambda: cs.submit(
        email=str(getattr(rec, "email", "") or ""),
        subject=z["тема"], body=z["тело"],
        inn=str(z.get("inn") or "") or None,
        campaign_id=cid, recipient_id=rid, message_id=mid,
        panel=panel))
    if r is None:
        print(f"  #{rid}: очередь не приняла - {str(сбой)[:100]}")
        continue
    положено += 1 if str(getattr(r, "status", "")) == "pending" else 0
    print(f"  #{rid} {str(z.get('имя'))[:30]:<32} -> "
          f"{getattr(r, 'status', '?')} #{getattr(r, 'review_id', '?')}")
print(f"\nдоложено в очередь: {положено} из {len(есть_текст)}")
