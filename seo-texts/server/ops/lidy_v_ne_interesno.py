# -*- coding: utf-8 -*-
"""Перевести лиды в «не интересно» (владелец 19.11: «если там полный отказ и нет запроса на доп. услуги — переведи в
не интересно»). Список id — по прочтению текстов ответов. Через LeadDesk.set_status (проверка перехода, CAS, аудит).
Журнал _ops/lidy-ne-interesno.jsonl (fsync).   lidy_v_ne_interesno.py <id,id,...> [--primenit]"""
import io, json, os, sys, time
sys.path.insert(0, r"C:\sender")
from sender.config import Config
from sender.store import Store
from sender.leaddesk import LeadDesk
ИДЫ = [int(x) for x in sys.argv[1].split(",") if x.strip()]
cfg = Config.load(r"C:\sender\sender.yaml"); st = Store(cfg.get("service.db_path", r"C:\sender\sender.db")); ld = LeadDesk(cfg, st)
итог = {}
with io.open(r"C:\sender\_ops\lidy-ne-interesno.jsonl", "a", encoding="utf-8") as ж:
    for и in ИДЫ:
        л = ld.get(и)
        if л is None: итог[и] = "нет лида"; continue
        if л.status != "new": итог[и] = "статус %s — не трогаю" % л.status; continue
        if "--primenit" not in sys.argv: итог[и] = "перевёл бы (%s, %s)" % (л.company_name, л.email); continue
        try:
            ld.set_status(и, status="not_interested")
            итог[и] = "ок"; ж.write(json.dumps({"lead": и, "email": л.email, "bylo": "new", "stalo": "not_interested", "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False) + "\n")
        except Exception as ex:  # noqa: BLE001
            итог[и] = "ошибка: %s" % ex
    ж.flush(); os.fsync(ж.fileno())
for и, v in итог.items(): print(и, v)
