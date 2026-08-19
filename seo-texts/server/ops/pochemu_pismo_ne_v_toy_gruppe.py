# -*- coding: utf-8 -*-
"""Почему письмо оказалось не в том направлении.

Владелец: «2646 письмо как то оказалось в группе мейер хотя это кц письмо».
Смотрим всё, что решает направление: кампанию строки, группы получателя,
метку базы (segment), ОКВЭД, и что об этом думает сама цепочка
target_division.
"""
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import target_division                     # noqa: E402
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

RID = int(next((a for a in sys.argv[1:] if a.isdigit()), "2646"))
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

row = store.confirm_get(RID) or {}
print(f"#{RID}  кампания {row.get('campaign_id')}  статус {row.get('status')}")
print(f"  адрес: {row.get('email')}  ИНН: {row.get('inn')}")
print(f"  тема: {row.get('subject')}")
print(f"  тело: {(row.get('body') or '')[:400]}")

rcid = row.get("recipient_id")
rec = store.get_recipient(int(rcid or 0))
if rec:
    print(f"\nполучатель #{rcid}: {getattr(rec, 'company_name', '')}")
    print(f"  ОКВЭД: {getattr(rec, 'okved', '')}")
    print(f"  segment (метка базы): {getattr(rec, 'segment', '')!r}")
    ex = getattr(rec, "extra_json", "") or ""
    try:
        d = json.loads(ex) if ex else {}
    except Exception:                                            # noqa: BLE001
        d = {}
    print(f"  extra.gruppy: {d.get('gruppy')!r}")
    print(f"  extra.activity: {str(d.get('activity') or '')[:80]!r}")

группы = store.recipient_groups().get("по_id") or {}
print(f"\nгруппы этого получателя: {sorted(группы.get(int(rcid or 0), []))}")

q = build_ai_quota(store, cfg)
try:
    req = q._request(rec)
    явное = str(req.get("target_division") or "")
    цепочка = target_division(req, default="kc")
    print(f"\nчто говорит цепочка направления:")
    print(f"  явное target_division в запросе: {явное!r}")
    print(f"  target_division(): {цепочка}")
except Exception as ex:                                          # noqa: BLE001
    print("запрос не собрался:", type(ex).__name__, str(ex)[:120])

панель = row.get("panel") if isinstance(row.get("panel"), dict) else {}
print(f"\nпанель письма: division={панель.get('division')!r} "
      f"напр_почему={панель.get('напр_почему')!r}")
