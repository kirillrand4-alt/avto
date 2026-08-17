# -*- coding: utf-8 -*-
"""Залить файлы пакета sender/ на сервер (C:\\sender\\sender\\...), без запуска.

Отдельно от vykatit_na_server.py: тот кладёт разовые скрипты в C:\\sender\\_ops,
а это боевой код панели и генератора - каталог другой, и цена ошибки другая.

ДВА ПУТИ ДОСТАВКИ, выбор по размеру. Инлайн-b64 прикладывается к самому
заданию и не требует от сервера HTTP-запроса наружу; но ai_letter.py весит
322КБ, в base64 это 429КБ, а внешний GET у сервера рвётся на 384КБ через
hairpin-NAT. Поэтому крупные файлы кладём на дроп как есть (322КБ проходят)
и передаём заданию только ИМЯ - серверная сторона скачает сама.

Перед заливкой ОБЯЗАТЕЛЬНО сверить sha256 серверной копии с той, от которой
правил: каталог делят несколько сессий (ops/sverit_sha_servera.py).

    python vykatit_sender.py ai_letter.py ai_quota.py
"""
import base64
import hashlib
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_on_server as R  # noqa: E402

ИСХОД = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "sender")
ПОРОГ_ИНЛАЙНА = 250_000            # байт исходника; b64 раздувает в 1.34 раза
DROP = os.environ.get("DROP_URL", "").rstrip("/")
ТОКЕН = os.environ.get("DROP_TOKEN", "")

имена = sys.argv[1:]
if not имена:
    print("нечего заливать: укажи файлы пакета sender/", file=sys.stderr)
    raise SystemExit(2)

файлы = []
for имя in имена:
    путь = os.path.join(ИСХОД, имя)
    blob = open(путь, "rb").read()
    dest = r"C:\sender\sender" + "\\" + имя.replace("/", "\\")
    ша = hashlib.sha256(blob).hexdigest()
    if len(blob) <= ПОРОГ_ИНЛАЙНА:
        файлы.append({"dest": dest, "b64": base64.b64encode(blob).decode()})
        путь_доставки = "инлайном"
    else:
        имя_на_дропе = "VYKATKA-" + os.path.basename(имя)
        rq = urllib.request.Request(f"{DROP}/{имя_на_дропе}", data=blob,
                                    method="PUT",
                                    headers={"X-Drop-Token": ТОКЕН})
        with urllib.request.urlopen(rq, timeout=180) as r:
            r.read()
        файлы.append({"dest": dest, "drop": имя_на_дропе})
        путь_доставки = f"через дроп ({имя_на_дропе})"
    print(f"{имя}: {len(blob)}б sha256={ша[:16]}… -> {dest} {путь_доставки}")

res = R.submit("enrich_contacts", {"op": "panel_file_put", "files": файлы},
               wait=True, poll=8, timeout=600)
d = (res or {}).get("data") or {}
print("ответ сервера:", d or res)
готово = (d.get("done") or []) if isinstance(d, dict) else []
ошибки = (d.get("errors") or d.get("errs") or []) if isinstance(d, dict) else []
print(f"залито: {len(готово)} | ошибок: {len(ошибки)}")
if ошибки:
    raise SystemExit(1)
