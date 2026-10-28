# -*- coding: utf-8 -*-
"""Поиск ЛПР по одной компании (владелец 28.10: «Вкусная жизнь» — менеджер не может
пробиться, «пиши письмо»): ЕГРЮЛ через dadata (руководитель, учредители, почта,
телефоны) + контакты из вакансий hh.ru (дельфин, мобильные прокси). Только чтение,
результат — на дроп lpr-<ИНН>.json.
    poisk_lpr.py <ИНН> "<название>" <сайт>"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, r"C:\sender\server")
import enrich_contacts as EC  # noqa: E402
import requests  # noqa: E402

инн, имя, сайт = sys.argv[1], sys.argv[2], sys.argv[3]
итог = {"inn": инн}
tok = EC._read_secret("DADATA_TOKEN")
if tok:
    try:
        req = urllib.request.Request(
            "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party",
            data=json.dumps({"query": инн}).encode(), method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json", "Authorization": "Token " + tok})
        d = json.loads(urllib.request.urlopen(req, timeout=25).read())
        s = ((d.get("suggestions") or [{}])[0].get("data") or {})
        итог["egrul"] = {"management": s.get("management"), "founders": s.get("founders"), "managers": s.get("managers"),
                         "emails": s.get("emails"), "phones": s.get("phones"), "okved": s.get("okved"),
                         "employee_count": s.get("employee_count"), "address": ((s.get("address") or {}).get("value"))}
    except Exception as ex:  # noqa: BLE001
        итог["egrul_err"] = str(ex)[:200]
else:
    итог["egrul_err"] = "нет DADATA_TOKEN"
try:
    EC._DOLPHIN_TOKEN = EC._read_secret("DOLPHIN_TOKEN") or ""
    итог["hh"] = EC.hh_lpr_contacts({"inn": инн, "name": имя, "site": сайт})
except Exception as ex:  # noqa: BLE001
    итог["hh_err"] = str(ex)[:300]
т = json.dumps(итог, ensure_ascii=False, indent=1, default=str)
requests.put(os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/") + "/lpr-%s.json" % инн,
             data=т.encode("utf-8"), headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=60)
print(т[:5000])
