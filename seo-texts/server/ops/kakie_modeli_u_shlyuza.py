# -*- coding: utf-8 -*-
"""Какие модели вообще есть на шлюзе — прежде чем обещать «дешевле».

Владелец 16.08 выбрал opus-4-8 не по цене: тарифы opus и fable на роутере
одинаковые. Значит «увести проверки на модель попроще» имеет смысл, только
если на шлюзе есть что-то ДЕШЕВЛЕ, и это надо не предполагать, а спросить.
"""
import json
import os
import urllib.request

БАЗА = os.environ.get("PROVIDER_BASE_URL", "https://router.cheap").rstrip("/")
КЛЮЧ = os.environ.get("PROVIDER_API_KEY", "")
for путь in ("/v1/models", "/v1/model", "/api/models"):
    try:
        r = urllib.request.Request(БАЗА + путь, headers={
            "x-api-key": КЛЮЧ, "authorization": f"Bearer {КЛЮЧ}",
            "anthropic-version": "2023-06-01", "User-Agent": "curl/8.5.0"})
        with urllib.request.urlopen(r, timeout=40) as o:
            d = json.loads(o.read().decode("utf-8", "replace"))
        имена = []
        данные = d.get("data") if isinstance(d, dict) else d
        for m in (данные or []):
            имена.append(m.get("id") or m.get("name") if isinstance(m, dict) else str(m))
        print(f"{путь}: {len(имена)} моделей")
        for i in sorted(x for x in имена if x):
            print("   ", i)
        break
    except Exception as ex:                                       # noqa: BLE001
        print(f"{путь}: {type(ex).__name__} {str(ex)[:120]}")
