# -*- coding: utf-8 -*-
"""Можно ли вообще заставить шлюз читать кэш: перебор вариантов запроса.

Опыт показал: шлюз пишет префикс на КАЖДОМ вызове (11 828 токенов) и
возвращает 28 токенов «чтения» — то есть кэш не отдаётся никогда. Прежде
чем предлагать выключить кэш (сейчас он делает вход дороже: запись 1.25
ставки против 1.0 без кэша), проверяем все ручки, какие есть:

  1. как сейчас        — cache_control без ttl;
  2. ttl=5m / ttl=1h   — продлённый кэш задаётся в запросе (ответ поддержки 19.08);
  3. beta-заголовки    — старый prompt-caching и extended-cache-ttl;
  4. без кэша вовсе    — контроль: сколько тогда числится входом.

Каждый вариант — ДВА вызова подряд на одном префиксе. Кэш работает, если на
втором запись падает до нуля, а чтение подскакивает до размера префикса.
"""
import os
import sys
import time

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

import gen_provider                                            # noqa: E402
from sender.ai_letter import gen_prompt, load_facts            # noqa: E402
from sender.ai_quota import build_ai_quota                     # noqa: E402
from sender.config import Config                               # noqa: E402
from sender.store import Store                                 # noqa: E402

МОДЕЛЬ = "claude-opus-4-8"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
группы = store.recipient_groups().get("по_id") or {}
rid = next((r for r, gr in sorted(группы.items()) if "Партия 935" in gr), None)
req = q._request(store.get_recipient(rid))
СИС, _ = gen_provider.razrezat_promt(
    gen_prompt([req], load_facts(division="kc"), "kc"))
print("префикс: %d знаков" % len(СИС))
ВОПРОС = [{"role": "user", "content": "Ответь одним словом: ок"}]
ИСХОДНЫЕ = dict(gen_provider._RAW_HEADERS)


def один(система, кэш=True):
    т0 = time.time()
    m = gen_provider._raw_stream(ВОПРОС, МОДЕЛЬ, 32, thinking=False,
                                 effort="low", system=система,
                                 cache_system=кэш)
    u = getattr(m, "usage", None)
    return (int(getattr(u, "input_tokens", 0) or 0),
            int(getattr(u, "cache_creation_input_tokens", 0) or 0),
            int(getattr(u, "cache_read_input_tokens", 0) or 0),
            time.time() - т0)


def опыт(имя, ttl=None, beta=None, кэш=True):
    if ttl:
        os.environ["LETTER_CACHE_TTL"] = ttl
    else:
        os.environ.pop("LETTER_CACHE_TTL", None)
    gen_provider._RAW_HEADERS.clear()
    gen_provider._RAW_HEADERS.update(ИСХОДНЫЕ)
    if beta:
        gen_provider._RAW_HEADERS["anthropic-beta"] = beta
    print("\n=== %s ===" % имя)
    итоги = []
    for н in (1, 2):
        try:
            вх, зап, чт, сек = один(СИС, кэш)
            итоги.append((зап, чт))
            print("  вызов %d: вход %-6d запись %-7d чтение %-7d  %.1fс%s"
                  % (н, вх, зап, чт, сек,
                     "   ← КЭШ ОТДАН" if чт > 1000 else ""))
        except Exception as e:  # noqa: BLE001
            print("  вызов %d: СБОЙ %s: %s" % (н, type(e).__name__, str(e)[:110]))
            итоги.append((-1, -1))
    сработал = len(итоги) > 1 and итоги[1][1] > 1000
    print("  ВЫВОД: %s" % ("кэш ЧИТАЕТСЯ" if сработал else "кэш НЕ читается"))
    return сработал


ok = {}
ok["как сейчас"] = опыт("1. КАК СЕЙЧАС (cache_control без ttl)")
ok["ttl=5m"] = опыт("2. ttl=5m", ttl="5m")
ok["ttl=1h"] = опыт("3. ttl=1h", ttl="1h")
ok["beta prompt-caching"] = опыт("4. beta: prompt-caching-2024-07-31",
                                 beta="prompt-caching-2024-07-31")
ok["beta extended-ttl"] = опыт("5. beta: extended-cache-ttl-2025-04-11 + ttl=1h",
                               ttl="1h", beta="extended-cache-ttl-2025-04-11")
ok["без кэша"] = опыт("6. БЕЗ КЭША (контроль: чем числится вход)", кэш=False)

gen_provider._RAW_HEADERS.clear()
gen_provider._RAW_HEADERS.update(ИСХОДНЫЕ)
os.environ.pop("LETTER_CACHE_TTL", None)

print("\n=== ИТОГ ===")
for к, з in ok.items():
    print("  %-26s %s" % (к, "ЧИТАЕТСЯ" if з else "нет"))
