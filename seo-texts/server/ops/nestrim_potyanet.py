# -*- coding: utf-8 -*-
"""Потянет ли нестрим настоящий объём: письмо на 2000 токенов выхода."""
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, r"C:\sender")
r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "Where-Object { $_.CommandLine -like '*partiya_gen*' } | "
                    "ForEach-Object { $i=$_.ProcessId; Stop-Process -Id $i -Force; \"убит $i\" }"],
                   capture_output=True, text=True, timeout=120)
print("остановка блока: %s" % ((r.stdout or "").strip() or "нечего"))

база = os.environ.get("PROVIDER_BASE_URL", "https://router.cheap").rstrip("/")
ключ = os.environ.get("PROVIDER_API_KEY", "")
ЗАДАЧИ = (
    ("короткий", "ответь одним словом: готов", 200, None),
    ("с system + JSON", "Компания: ООО «Ромашка», делает крупы. Ответь JSON.",
     2000, "Ты классификатор. Ответ строго JSON: {\"ok\":true}"),
    ("объём письма", "Напиши деловое письмо на 150 слов о поставке "
                     "промышленного оборудования пищевому производству.",
     2000, None),
)
for имя, вопрос, потолок, sys_ in ЗАДАЧИ:
    тело = {"model": "claude-sonnet-4-6", "max_tokens": потолок,
            "messages": [{"role": "user", "content": вопрос}]}
    if sys_:
        тело["system"] = sys_
    з = urllib.request.Request(база + "/v1/messages",
                               data=json.dumps(тело).encode("utf-8"),
                               method="POST")
    з.add_header("content-type", "application/json")
    з.add_header("x-api-key", ключ)
    з.add_header("anthropic-version", "2023-06-01")
    з.add_header("User-Agent", "curl/8.5.0")
    т0 = time.time()
    try:
        with urllib.request.urlopen(з, timeout=240) as о:
            d = json.loads(о.read().decode("utf-8", "replace"))
        текст = "".join(к.get("text") or "" for к in (d.get("content") or [])
                        if к.get("type") == "text")
        u = d.get("usage") or {}
        print("   %-18s ОК за %6.1f с, выход %s токенов, ответ %r"
              % (имя, time.time() - т0, u.get("output_tokens"), текст[:50]))
    except Exception as e:                                     # noqa: BLE001
        print("   %-18s ОШИБКА за %6.1f с: %s"
              % (имя, time.time() - т0, str(e)[:110]))

print("\n=== ИТОГ ===")
print("если нестрим отвечает за секунды на всех трёх — конвейер можно")
print("перевести на него и работать ночью, пока стрим у шлюза лежит.")
