# -*- coding: utf-8 -*-
"""Опыт: какой вариант запроса реально выключает рассуждение на канале шлюза.

Владелец 12.10: «разберись, когда уходит в размышления и как их отключить».
Генератор уже шлёт thinking={'type':'disabled'} (решение 17.08), но канал
Claude Kiro всё равно рассуждает. Один промпт, несколько вариантов тела
запроса; по каждому — знаки рассуждения, знаки текста, токены выхода.
"""
import json
import sys
import time

import httpx

sys.path.insert(0, r"C:\sender")
import gen_provider as GP  # noqa: E402

e = GP.env()
БАЗА = e["PROVIDER_BASE_URL"].rstrip("/")
КЛЮЧ = e["PROVIDER_API_KEY"]
ПРОМПТ = ("Ниже карточка компании. Оцени по пунктам 1-3, может ли она купить "
          "фотосепаратор или рентген-инспекцию, и верни СТРОГО JSON "
          '{"verdict":"верно|сомнительно|ошибка","pochemu":"одна фраза"}.\n\n'
          "Компания: ООО «Сибирская мука». Паспорт сайта: продукция — мука "
          "пшеничная высшего и первого сорта, мука ржаная обдирная, отруби; "
          "сырьё — пшеница 3-4 класса, рожь; мощности — 300 т зерна в сутки; "
          "оборудование линий — вальцовые станки, рассевы, ситовеечные "
          "машины, обоечные машины; контроль качества — лаборатория, "
          "клейковина, число падения; упаковка — мешки 50 кг, пакеты 2 кг.\n"
          "1) сама производит или продаёт такое оборудование?\n"
          "2) есть ли поток продукта, который сортируют или фасуют?\n"
          "3) приписано ли ей то, чего нет в паспорте?")


def anthropic(модель, тело_доп):
    тело = {"model": модель, "max_tokens": 1500, "stream": True,
            "messages": [{"role": "user", "content": ПРОМПТ}]}
    тело.update(тело_доп)
    з = dict(GP._RAW_HEADERS)
    з["x-api-key"] = КЛЮЧ
    дума = текст = 0
    вых = None
    with httpx.stream("POST", БАЗА + "/v1/messages", headers=з, json=тело,
                      timeout=180.0) as r:
        if r.status_code != 200:
            return "HTTP %s %s" % (r.status_code, r.read().decode("utf-8", "replace")[:160])
        for стр in r.iter_lines():
            if not стр.startswith("data:"):
                continue
            try:
                д = json.loads(стр[5:])
            except Exception:  # noqa: BLE001
                continue
            if д.get("type") == "content_block_delta":
                дл = д.get("delta") or {}
                if дл.get("type") == "thinking_delta":
                    дума += len(дл.get("thinking") or "")
                elif дл.get("type") == "text_delta":
                    текст += len(дл.get("text") or "")
            if д.get("type") == "message_delta":
                вых = (д.get("usage") or {}).get("output_tokens", вых)
    return "выход %s ток | рассуждение %d зн | текст %d зн" % (вых, дума, текст)


def openai(модель, тело_доп):
    тело = {"model": модель, "max_tokens": 1500, "stream": True,
            "stream_options": {"include_usage": True},
            "messages": [{"role": "user", "content": ПРОМПТ}]}
    тело.update(тело_доп)
    з = {"Authorization": "Bearer " + КЛЮЧ, "content-type": "application/json",
         "User-Agent": "curl/8.5.0"}
    дума = текст = 0
    вых = None
    with httpx.stream("POST", БАЗА + "/v1/chat/completions", headers=з,
                      json=тело, timeout=180.0) as r:
        if r.status_code != 200:
            return "HTTP %s %s" % (r.status_code, r.read().decode("utf-8", "replace")[:160])
        for стр in r.iter_lines():
            if not стр.startswith("data:") or стр.strip() == "data: [DONE]":
                continue
            try:
                д = json.loads(стр[5:])
            except Exception:  # noqa: BLE001
                continue
            for в in д.get("choices") or []:
                дл = в.get("delta") or {}
                текст += len(дл.get("content") or "")
                дума += len(дл.get("reasoning_content") or дл.get("reasoning") or "")
            if д.get("usage"):
                вых = д["usage"].get("completion_tokens", вых)
    return "выход %s ток | рассуждение %d зн | текст %d зн" % (вых, дума, текст)


ВАРИАНТЫ_ПОЛНЫЕ = [
    ("A запрет + усилие low (как письма)", anthropic,
     {"thinking": {"type": "disabled"}, "output_config": {"effort": "low"}}),
    ("B запрет, без усилия (как гейт)", anthropic, {"thinking": {"type": "disabled"}}),
    ("C поля thinking нет вовсе", anthropic, {}),
    ("D включено, бюджет 1024", anthropic,
     {"thinking": {"type": "enabled", "budget_tokens": 1024}}),
    ("E дверь OpenAI, без параметров", openai, {}),
    ("F дверь OpenAI, reasoning_effort=none", openai, {"reasoning_effort": "none"}),
]
# Второй заход (12.10): без поля thinking, но с усилием — так пишутся письма.
ВАРИАНТЫ = [
    ("C поля thinking нет вовсе", anthropic, {}),
    ("G поля нет, усилие low", anthropic, {"output_config": {"effort": "low"}}),
    ("H поля нет, усилие medium", anthropic, {"output_config": {"effort": "medium"}}),
] if "--vtoroy" in sys.argv else ВАРИАНТЫ_ПОЛНЫЕ
модели = [м for м in sys.argv[1:] if not м.startswith("--")] or ["claude-sonnet-4-6"]
for модель in модели:
    print("=== %s ===" % модель)
    for имя, f, доп in ВАРИАНТЫ:
        t = time.time()
        try:
            итог = f(модель, доп)
        except Exception as ex:  # noqa: BLE001
            итог = "СБОЙ %s" % str(ex)[:120]
        print("   %-36s %5.1f с | %s" % (имя, time.time() - t, итог))
print("=== ОПЫТ РАССУЖДЕНИЯ ===")
