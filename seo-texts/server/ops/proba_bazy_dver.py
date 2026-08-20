# -*- coding: utf-8 -*-
"""Новый шлюз через OpenAI-дверь: живость, кэш, скорость, цена входа.

Anthropic-дверь (/v1/messages) у него 404 — значит вся клодовская линия
идёт по /v1/chat/completions. Кэш там показывают полем
usage.prompt_tokens_details.cached_tokens.
"""
import json
import os
import sys
import time
import urllib.request

БАЗА = "https://api.baza-ai.org/v1"
КЛЮЧ = open(os.environ.get("BAZA_KEY", r"C:\sender\baza.key"),
            encoding="utf-8").read().strip()
# Статика заведомо длиннее порога кэша.
СИСТЕМА = ("Ты редактор холодных B2B-писем промышленной компании. "
           "Правила: без длинных тире, без списков, числа только из фактов. "
           * 150)


def зов(модель, вопрос="Ответь одним словом: да", поток=False):
    тело = {"model": модель, "max_tokens": 64, "stream": поток,
            "messages": [{"role": "system", "content": СИСТЕМА},
                         {"role": "user", "content": вопрос}]}
    зпр = urllib.request.Request(
        БАЗА + "/chat/completions", data=json.dumps(тело).encode(),
        headers={"content-type": "application/json",
                 "authorization": "Bearer " + КЛЮЧ,
                 "User-Agent": "curl/8.5.0"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(зпр, timeout=180) as о:
            сыро = о.read()
    except urllib.error.HTTPError as ex:
        return {"ошибка": f"HTTP {ex.code}: "
                          f"{ex.read()[:200].decode('utf-8', 'replace')}",
                "сек": round(time.time() - t0, 1)}
    except Exception as ex:                                      # noqa: BLE001
        return {"ошибка": f"{type(ex).__name__}: {str(ex)[:140]}",
                "сек": round(time.time() - t0, 1)}
    д = json.loads(сыро)
    u = д.get("usage") or {}
    дет = u.get("prompt_tokens_details") or {}
    вых = ((д.get("choices") or [{}])[0].get("message") or {}).get("content")
    return {"сек": round(time.time() - t0, 1), "вход": u.get("prompt_tokens"),
            "выход": u.get("completion_tokens"),
            "кэш_чтение": дет.get("cached_tokens"),
            "текст": str(вых)[:50]}


for м in (sys.argv[1:] or ["claude-opus-4-8"]):
    print(f"\n=== {м} ===")
    for i in (1, 2, 3):
        print(f"  вызов {i}: {зов(м)}")
