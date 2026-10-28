# -*- coding: utf-8 -*-
"""ЛПР компании через поиск Яндекса (xmlriver) + разбор выдачи моделью провайдера
(владелец 28.10: «поиск начинай, в идеале через провайдера, направление Meyer»).
Запросы: технолог/качество/производство/директор/почта + название + город.
Модель вытаскивает ТОЛЬКО то, что прямо есть в сниппетах: ФИО, должность, почта,
телефон, источник. Ничего не отправляет. Итог — на дроп lpr-web-<ИНН>.json.
    poisk_lpr_web.py <ИНН> "<название без ООО>" <город> <сайт> "<запрос>;<запрос>..." """
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, r"C:\sender\server")
import enrich_contacts as EC  # noqa: E402
import gen_provider as GP     # noqa: E402
import requests               # noqa: E402

инн, имя, город, сайт = sys.argv[1:5]
запросы = [q.strip() for q in sys.argv[5].split(";") if q.strip()]
user, key = os.environ.get("XMLRIVER_USER", ""), os.environ.get("XMLRIVER_KEY", "")
выдача = []
for q in запросы:
    url = ("http://xmlriver.com/search_yandex/xml?user=" + urllib.parse.quote(user) + "&key=" + urllib.parse.quote(key)
           + "&domain=ru&device=desktop&query=" + urllib.parse.quote(q))
    try:
        xml = EC._DIRECT.open(url, timeout=40).read().decode("utf-8", "replace")
    except Exception as ex:  # noqa: BLE001
        выдача.append({"q": q, "err": str(ex)[:100]})
        continue
    for doc in re.findall(r"<doc>(.*?)</doc>", xml, re.S)[:10]:
        u = (re.search(r"<url>(.*?)</url>", doc, re.S) or [None, ""])[1]
        t = re.sub(r"<[^>]+>", "", (re.search(r"<title>(.*?)</title>", doc, re.S) or [None, ""])[1])
        p = re.sub(r"<[^>]+>", " ", " ".join(re.findall(r"<passage>(.*?)</passage>", doc, re.S)))
        выдача.append({"q": q, "url": u.strip(), "title": t.strip(), "text": re.sub(r"\s+", " ", p).strip()[:600]})
ЗАДАНИЕ = """Компания: %s (ИНН %s, %s, сайт %s), мясопереработка. Ниже — выдача Яндекса.
Найди людей и контакты ЭТОЙ компании (не однофамильцев и не других фирм с похожим названием):
ФИО, должность, email, телефон, источник (url). Особенно: технолог, служба качества, производство,
главный инженер, закупки, руководство. Бери ТОЛЬКО то, что прямо написано в выдаче, ничего не выдумывай.
Если сомневаешься, что это та же компания, — поставь "уверенность": "низкая".
Ответ СТРОГО JSON: {"lyudi":[{"fio":"","dolzhnost":"","email":"","telefon":"","istochnik":"","uverennost":"высокая|низкая"}],
"pochty_kompanii":[], "telefony_kompanii":[], "zametki":""}

ВЫДАЧА:
%s"""
текст = "\n\n".join("[%s] %s\n%s\n%s" % (в.get("q"), в.get("url"), в.get("title"), в.get("text")) for в in выдача if в.get("url"))
итог = {"inn": инн, "zaprosov": len(запросы), "dokumentov": len(выдача)}
try:
    m = GP._raw_stream([{"role": "user", "content": ЗАДАНИЕ % (имя, инн, город, сайт, текст[:60000])}],
                       "claude-sonnet-4-6", 3000, thinking=False, effort="low")
    т = m if isinstance(m, str) else "".join(getattr(b, "text", "") for b in getattr(m, "content", []) or [])
    вх = [x.start() for x in re.finditer(r'\{\s*"lyudi"', т)]
    итог["razbor"] = json.JSONDecoder(strict=False).raw_decode(т[вх[-1]:])[0] if вх else {"syroy": т[-1500:]}
except Exception as ex:  # noqa: BLE001
    итог["razbor_err"] = str(ex)[:200]
итог["vydacha"] = выдача
т = json.dumps(итог, ensure_ascii=False, indent=1)
requests.put(os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/") + "/lpr-web-%s.json" % инн,
             data=т.encode("utf-8"), headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=60)
print(json.dumps(итог.get("razbor") or итог.get("razbor_err"), ensure_ascii=False, indent=1)[:5000])
