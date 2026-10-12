# -*- coding: utf-8 -*-
"""Забрать журнал вызовов шлюза по нашему ключу (только чтение).

Шлюз собран на движке New API: у него есть запрос журнала по ключу
(/api/log/token?key=…). Пробуем его, ничего не меняя. Ключ не печатаем.
"""
import json
import os
import urllib.request

база = os.environ.get("PROVIDER_BASE_URL", "https://router.cheap").rstrip("/")
ключ = os.environ.get("PROVIDER_API_KEY", "")
print("ключ в окружении: %s" % ("есть" if ключ else "НЕТ"))
for путь in ("/api/log/token?key=%s" % ключ,
             "/api/log/token?key=%s" % ключ.replace("sk-", "", 1)):
    try:
        з = urllib.request.Request(база + путь, headers={
            "User-Agent": "curl/8.5.0", "Accept": "application/json"})
        with urllib.request.urlopen(з, timeout=30) as о:
            т = о.read().decode("utf-8", "replace")
        д = json.loads(т)
        данные = д.get("data")
        print("ответ: success=%s, тип data=%s, записей=%s"
              % (д.get("success"), type(данные).__name__,
                 len(данные) if isinstance(данные, list) else "—"))
        if isinstance(данные, list) and данные:
            print("поля записи: %s" % sorted(данные[0].keys()))
            break
        print("сообщение: %s" % str(д.get("message"))[:200])
    except Exception as e:  # noqa: BLE001
        print("путь не сработал: %s" % str(e)[:160])
print("=== ЖУРНАЛ ШЛЮЗА ===")
