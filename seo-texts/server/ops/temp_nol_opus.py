# -*- coding: utf-8 -*-
"""Решающая проба: одинаков ли бэкенд за именами опусов, при temperature=0.

Прошлая сверка была негодной: выборка идёт с температурой, и ни одно имя
не повторило даже само себя - значит совпадений не было бы и у заведомо
одного бэкенда. При нуле температуры argmax детерминирован, и правило
читается однозначно:
  * имя не повторяет СЕБЯ  -> шлюз температуру игнорирует, путь закрыт;
  * имена повторяют себя, но отличаются друг от друга -> бэкенды разные;
  * два имени дословно совпали -> за ними один бэкенд.
Промпт нарочно творческий: у фактического вопроса ответы совпали бы у
любых моделей и ничего не доказали бы.
"""
import hashlib
import json
import sys

import httpx

sys.path.insert(0, r"C:\sender")
import gen_provider                                           # noqa: E402

ПРОМПТ = ("Напиши ровно два предложения о том, почему зимой в компрессорной "
          "падает производительность. Без вступлений и списков.")
ИМЕНА = ["claude-opus-4-6", "claude-opus-4-7",
         "claude-opus-4-8", "claude-opus-5"]

e = gen_provider.env()
url = e["PROVIDER_BASE_URL"].rstrip("/") + "/v1/messages"
шапка = dict(gen_provider._RAW_HEADERS)
шапка["x-api-key"] = e["PROVIDER_API_KEY"]

группы = {}
for имя in ИМЕНА:
    for попытка in (1, 2):
        тело = {"model": имя, "max_tokens": 300, "temperature": 0,
                "thinking": {"type": "disabled"},
                "messages": [{"role": "user", "content": ПРОМПТ}]}
        try:
            r = httpx.post(url, headers=шапка, json=тело, timeout=300.0)
            if r.status_code != 200:
                print(f"{имя} #{попытка}: HTTP {r.status_code} "
                      f"{r.text[:120]}")
                continue
            д = r.json()
            т = "".join(б.get("text", "") for б in д.get("content") or []
                        if б.get("type") == "text").strip()
            u = д.get("usage") or {}
        except Exception as ex:                               # noqa: BLE001
            print(f"{имя} #{попытка}: СБОЙ {str(ex)[:100]}")
            continue
        х = hashlib.sha256(т.encode()).hexdigest()[:12]
        группы.setdefault(х, []).append(f"{имя}#{попытка}")
        print(f"{имя} #{попытка}: sha={х} вх={u.get('input_tokens')} "
              f"вых={u.get('output_tokens')}")
        print(f"    {т[:170]}")

print("\nгруппы дословно одинаковых ответов:")
for х, кто in группы.items():
    print(f"  {х}: {', '.join(кто)}")

сам_себя = [к for к in группы.values() if len(к) > 1
            and len({и.split('#')[0] for и in к}) == 1]
разные = [к for к in группы.values()
          if len({и.split('#')[0] for и in к}) > 1]
print()
if разные:
    for г in разные:
        print("ОДИН БЭКЕНД: " + ", ".join(sorted({и.split('#')[0]
                                                  for и in г})))
elif сам_себя:
    print("температура работает (имена повторяют себя), "
          "но разные имена не совпали — бэкенды РАЗНЫЕ")
else:
    print("ни одно имя не повторило себя — шлюз игнорирует temperature=0, "
          "этим способом вопрос не решается")
