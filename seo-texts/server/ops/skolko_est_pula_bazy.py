# -*- coding: utf-8 -*-
"""Во что обходится вызов в токенах пула: замер счётчика до и после.

Шлюз продаёт не доллары, а пул токенов (/v1/usage: quota_tokens). Значит
множители с карточек моделей (×6 у опуса, ×1.6 у соннета) — это скорость,
с которой модель ест пул. Проверяем на деле: считываем остаток, делаем
вызов с известным входом и выходом, считываем снова.
"""
import json
import os
import time
import urllib.request

БАЗА = "https://api.baza-ai.org/v1"
КЛЮЧ = open(os.environ.get("BAZA_KEY", r"C:\sender\baza.key"),
            encoding="utf-8").read().strip()
ГОЛОВА = {"authorization": "Bearer " + КЛЮЧ, "content-type": "application/json",
          "User-Agent": "curl/8.5.0"}
СИСТЕМА = ("Ты редактор холодных B2B-писем промышленной компании. "
           "Правила: без длинных тире, без списков, числа только из фактов. "
           * 150)


def расход():
    зпр = urllib.request.Request(БАЗА + "/usage", headers=ГОЛОВА)
    with urllib.request.urlopen(зпр, timeout=60) as о:
        д = json.loads(о.read())
    return int(д["used_tokens"]), int(д["remaining_tokens"])


def зов(модель, сколько_выхода=200):
    тело = {"model": модель, "max_tokens": сколько_выхода,
            "messages": [{"role": "system", "content": СИСТЕМА},
                         {"role": "user",
                          "content": "Напиши ровно 120 слов про сжатый воздух "
                                     "на производстве."}]}
    зпр = urllib.request.Request(БАЗА + "/chat/completions",
                                 data=json.dumps(тело).encode(), headers=ГОЛОВА)
    t0 = time.time()
    with urllib.request.urlopen(зпр, timeout=180) as о:
        д = json.loads(о.read())
    u = д.get("usage") or {}
    return (int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0),
            round(time.time() - t0, 1))


print(f"{'модель':<20} {'вход':>7} {'выход':>6} {'списано':>9} "
      f"{'множ':>6} {'сек':>5}")
for м in ("claude-opus-4-8", "claude-opus-5", "claude-sonnet-5",
          "claude-haiku-4-5", "gpt-5.4-mini", "gemini-3-flash"):
    до, _ = расход()
    try:
        вх, вых, сек = зов(м)
    except Exception as ex:                                      # noqa: BLE001
        print(f"{м:<20} СБОЙ: {type(ex).__name__} {str(ex)[:70]}")
        continue
    time.sleep(2)
    после, ост = расход()
    списано = после - до
    сыро = вх + вых
    мн = round(списано / сыро, 2) if сыро else 0
    print(f"{м:<20} {вх:>7} {вых:>6} {списано:>9} {мн:>6} {сек:>5}")
print("\nостаток пула:", расход()[1])
