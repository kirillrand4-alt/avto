# -*- coding: utf-8 -*-
"""Почему пять писем старых кампаний не переписываются: полные претензии.

regenerate_review возвращает не только «генерация забракована», но и
список fails — то, на чём споткнулись гейты. Мой прогон переписи писал в
журнал одну метку, и причина терялась. Смотрим её целиком.
"""
import sys

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ИДЫ = [int(a) for a in sys.argv[1:] if a.isdigit()]
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

for rid in ИДЫ:
    row = store.confirm_get(rid) or {}
    имя = str(row.get("company_name") or "")[:40]
    статус = row.get("status")
    if статус != "pending":
        print(f"#{rid} {имя} — статус {статус}, не трогаю")
        continue
    try:
        res = q.regenerate_review(rid)
    except Exception as ex:                                      # noqa: BLE001
        print(f"#{rid} {имя} — сбой {type(ex).__name__}: {str(ex)[:120]}")
        continue
    print(f"#{rid} {имя} — ok={res.get('ok')} "
          f"{'СНЯТО КАК НЕ НАШ' if res.get('снято_как_не_наш') else ''}")
    for f in (res.get("fails") or []):
        print(f"     · {str(f)[:200]}")
