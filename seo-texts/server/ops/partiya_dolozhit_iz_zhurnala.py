# -*- coding: utf-8 -*-
"""Доложить в очередь письма, которые есть в журнале, но не попали в панель.

Страховка к тому, что текст письма теперь пишется в журнал ДО постановки в
очередь. Если база была занята и запись не прошла, письмо всё равно цело -
берём его отсюда и кладём, не платя модели второй раз.

СЧИТАЕМ ПО КОМПАНИЯМ, А НЕ ПО СТРОКАМ. С 17.08 на одно письмо в журнале
ДВЕ строки: «сгенерировано» (текст есть, review_id ещё нет) и «итог» (уже
с review_id). Построчный обход принимал первую строку удачного письма за
потерянное и клал его второй раз. Дубль в очередь не проходит - store
дедуплицирует по dedup_key (ИНН+адрес+кампания) и вернёт существующую
строку, - но счёт «спасено» врал бы в разы, а на враньё в числах опираться
нельзя.

Три заслона от повторной постановки, каждый закрывает свою дыру:
  * review_id из журнала -> строка очереди с текстом уже есть;
  * ключ дедупа (ИНН+адрес+кампания) -> письмо легло, а журнал итога не
    успел записаться (падение между submit и строкой журнала);
  * порядок строк по компании - берём последнюю с текстом.

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
from sender.suppression import Suppression                     # noqa: E402

ПРИМЕНИТЬ = len(sys.argv) > 1 and sys.argv[1] == "primenit"
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
КАМПАНИЯ = {"kc": 10, "meyer": 11}

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
cs = ConfirmSend(cfg, store, Suppression(store))


def _с_повторами(что, *a, **kw):
    """Занятая база не должна ронять весь доклад. Работник пишет вердикты в
    ту же sqlite; «database is locked» здесь такая же норма, как в генераторе.
    Возвращает (результат, причина_отказа)."""
    почему = ""
    for поп in range(6):
        try:
            return что(*a, **kw), ""
        except Exception as ex:                                # noqa: BLE001
            почему = str(ex)[:110]
            if "locked" not in почему.lower() and поп >= 2:
                break
            time.sleep(2 + поп * 3)
    return None, почему


# --- разбор журнала ПО КОМПАНИЯМ -----------------------------------------
по_фирме = {}
строк = 0
for s in (io.open(ЖУРНАЛ, encoding="utf-8") if os.path.exists(ЖУРНАЛ) else []):
    try:
        z = json.loads(s)
    except Exception:                                          # noqa: BLE001
        continue
    строк += 1
    ключ = str(z.get("inn") or "") or f"rid:{z.get('recipient_id')}"
    по_фирме.setdefault(ключ, []).append(z)

потеряны, счёт = [], Counter()
for ключ, ряд in по_фирме.items():
    с_текстом = [z for z in ряд if z.get("тело")]
    if not с_текстом:
        счёт["текста письма нет вовсе"] += 1
        continue
    # Заслон 1: журнал сам знает review_id, и за ним стоит строка с текстом.
    легло = False
    for z in ряд:
        rev = z.get("review_id")
        if rev and ((store.confirm_get(int(rev)) or {}).get("body")):
            легло = True
            break
    if легло:
        счёт["уже в очереди (по review_id)"] += 1
        continue
    посл = с_текстом[-1]
    # Заслон 2: письмо легло, но строка итога не записалась. Ищем по тому же
    # ключу, каким дедуплицирует сама очередь.
    rid = посл.get("recipient_id")
    rec = store.get_recipient(int(rid)) if rid else None
    if rec is not None:
        div = str(посл.get("направление") or "kc")
        cid = КАМПАНИЯ.get(div, 10)
        почта = str(getattr(rec, "email", "") or "").strip().lower()
        было = store.confirm_get_by_key(
            str(посл.get("inn") or "") or None, почта, cid)
        if было and было.get("body"):
            счёт["уже в очереди (по ключу дедупа)"] += 1
            continue
    else:
        счёт["получателя нет в панели"] += 1
        continue
    потеряны.append((посл, rec))

print(f"строк журнала {строк} | компаний {len(по_фирме)}")
print(f"ПИСЕМ С ТЕКСТОМ, НО БЕЗ СТРОКИ ОЧЕРЕДИ: {len(потеряны)}")
for k, n in счёт.most_common():
    print(f"  {k:<32} {n}")

if not ПРИМЕНИТЬ or not потеряны:
    print("сухой прогон: ничего не менял" if not ПРИМЕНИТЬ
          else "докладывать нечего")
    raise SystemExit(0)

день = date.today().isoformat()
положено = 0
for z, rec in потеряны:
    rid = int(z["recipient_id"])
    div = str(z.get("направление") or "kc")
    cid = КАМПАНИЯ.get(div, 10)
    пара, почему = _с_повторами(q._ensure_message, cid, rid)
    mid = (пара or (None, None, ""))[0]
    if not mid:
        print(f"  #{rid}: нет message_id ({почему or (пара or ['', '', ''])[2]})")
        continue
    try:
        req = q._request(rec)
        req["target_division"] = div
        panel = q._panel(rec, {"subject": z["тема"], "body": z["тело"]},
                         день, req)
    except Exception:                                          # noqa: BLE001
        panel = {}
    r, почему = _с_повторами(
        cs.submit, email=str(getattr(rec, "email", "") or ""),
        subject=z["тема"], body=z["тело"],
        inn=str(z.get("inn") or "") or None,
        campaign_id=cid, recipient_id=rid, message_id=mid, panel=panel)
    if r is None:
        print(f"  #{rid}: очередь не приняла ({почему}), письмо ждёт в журнале")
        continue
    положено += 1 if str(getattr(r, "status", "")) == "pending" else 0
    print(f"  #{rid} {str(z.get('имя'))[:30]:<32} -> "
          f"{getattr(r, 'status', '?')} #{getattr(r, 'review_id', '?')}")
print(f"\nдоложено в очередь: {положено} из {len(потеряны)}")
