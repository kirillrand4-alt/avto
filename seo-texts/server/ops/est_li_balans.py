# -*- coding: utf-8 -*-
"""Хватит ли денег на НАСТОЯЩЕЕ письмо, а не на любой ответ вообще.

17.08 я объявил владельцу «баланс пополнен, перезапускаю» - и ошибся. Мой
пробный запрос просил max_tokens=8, шлюз посчитал его дешёвым и пропустил
(HTTP 200). Генерация же просит 4000 и получает отказ:

  balance: $0.025428, need: $0.080098

То есть шлюз резервирует деньги ПОД ПОТОЛОК ОТВЕТА, и маленькая проба
проходит там, где боевой вызов не проходит. Прогон я перезапустил зря: он
снова начал жечь компаниям попытки.

Отсюда правило: проба обязана просить столько же, сколько просит генерация
(ПОТОЛОК_ОТВЕТА в ops/partiya_gen.py). И ретраи выключены - на пустом
кошельке они превращают ответ в минуты ожидания.

    python zapusk_svoego_skripta.py ops/est_li_balans.py
    python zapusk_svoego_skripta.py ops/est_li_balans.py claude-opus-4-8 4000
"""
import json
import os
import sys
import urllib.error
import urllib.request

МОДЕЛЬ = sys.argv[1] if len(sys.argv) > 1 else "claude-opus-4-8"
ПОТОЛОК = int(sys.argv[2]) if len(sys.argv) > 2 else 4000

БАЗА = os.environ.get("PROVIDER_BASE_URL", "https://router.cheap").rstrip("/")
КЛЮЧ = os.environ.get("PROVIDER_API_KEY", "")
тело = json.dumps({
    "model": МОДЕЛЬ, "max_tokens": ПОТОЛОК,
    "messages": [{"role": "user", "content": "ответь одним словом: да"}],
}).encode()
req = urllib.request.Request(
    f"{БАЗА}/v1/messages", data=тело, method="POST",
    headers={"content-type": "application/json", "x-api-key": КЛЮЧ,
             "anthropic-version": "2023-06-01", "User-Agent": "curl/8.5.0"})

print(f"проба: модель {МОДЕЛЬ}, потолок ответа {ПОТОЛОК} "
      "(столько же просит генерация)")
try:
    with urllib.request.urlopen(req, timeout=90) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
        u = d.get("usage") or {}
        print(f"ДЕНЬГИ ЕСТЬ: HTTP {r.status}, модель ответа "
              f"{d.get('model')}, токенов {u}")
        raise SystemExit(0)
except urllib.error.HTTPError as ex:
    т = ex.read().decode("utf-8", "replace")
    print(f"HTTP {ex.code}: {т[:300]}")
    if "quota insufficient" in т or ex.code == 403:
        print("ДЕНЕГ НЕТ - прогон НЕ ЗАПУСКАТЬ: каждый 403 записывается как "
              "неудачная попытка и выбивает компанию из партии")
    else:
        print("другая ошибка шлюза")
    raise SystemExit(2)
except Exception as ex:                                         # noqa: BLE001
    print("шлюз не ответил:", type(ex).__name__, str(ex)[:200])
    raise SystemExit(3)
