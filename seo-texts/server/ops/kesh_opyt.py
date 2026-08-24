# -*- coding: utf-8 -*-
"""Почему кэш читается в одиночном замере и не читается в партии.

Префикс доказанно один и тот же (хеш статики совпадает у всех писем), а в
журнале партии каждый вызов ПИШЕТ кэш и ни один не читает. Значит ломает не
текст, а обстановка вызова. Разделяем три подозрения тремя опытами на одном
и том же реальном системном блоке КЦ:

  А. подряд, одинаковые параметры  — контроль: так замеряли 24.08;
  Б. восемь вызовов разом          — партия идёт в потоках, кэш может не
                                     успевать или уезжать на другой канал шлюза;
  В. подряд, но с чередованием     — в письме подряд идут разные префиксы
     двух разных префиксов            (генерация/верификатор/судья).

Ответ короткий («ок»), потолок выхода маленький — платим за вход, не за выход.
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

import gen_provider                                            # noqa: E402
from sender.ai_letter import gen_prompt, load_facts, vf_prompt  # noqa: E402
from sender.ai_quota import build_ai_quota                     # noqa: E402
from sender.config import Config                               # noqa: E402
from sender.store import Store                                 # noqa: E402

МОДЕЛЬ = "claude-opus-4-8"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
факты = load_facts(division="kc")

группы = store.recipient_groups().get("по_id") or {}
rid = next((r for r, gr in sorted(группы.items()) if "Партия 935" in gr), None)
rec = store.get_recipient(rid)
req = q._request(rec)
СИС_ГЕН, _ = gen_provider.razrezat_promt(gen_prompt([req], факты, "kc"))
СИС_ВФ, _ = gen_provider.razrezat_promt(vf_prompt(
    [(0, "тема", "тело письма")], "kc"))
print("системный генерации: %d знаков | верификатора: %s знаков"
      % (len(СИС_ГЕН), len(СИС_ВФ) if СИС_ВФ else "НЕТ РАЗРЕЗА"))
if not СИС_ВФ:
    СИС_ВФ = СИС_ГЕН[:len(СИС_ГЕН) // 2]
    print("  (у верификатора границы нет — для опыта берём половину гена)")

ВОПРОС = [{"role": "user", "content": "Ответь одним словом: ок"}]


def вызов(метка, система, усилие="low"):
    т0 = time.time()
    try:
        m = gen_provider._raw_stream(ВОПРОС, МОДЕЛЬ, 32, thinking=False,
                                     effort=усилие, system=система)
        u = getattr(m, "usage", None)
        зап = int(getattr(u, "cache_creation_input_tokens", 0) or 0)
        чт = int(getattr(u, "cache_read_input_tokens", 0) or 0)
        вх = int(getattr(u, "input_tokens", 0) or 0)
        print("  %-30s %5.1fс  вход %-6d запись %-7d ЧТЕНИЕ %-7d %s"
              % (метка, time.time() - т0, вх, зап, чт,
                 "✔ кэш прочитан" if чт else ""))
        return чт
    except Exception as e:  # noqa: BLE001
        print("  %-30s СБОЙ %s: %s" % (метка, type(e).__name__, str(e)[:90]))
        return -1


print("\n=== А. ПОДРЯД, ОДИНАКОВЫЕ ПАРАМЕТРЫ (контроль) ===")
а = [вызов("подряд #%d" % (i + 1), СИС_ГЕН) for i in range(3)]

print("\n=== Б. ВОСЕМЬ ВЫЗОВОВ РАЗОМ (как в партии) ===")
with ThreadPoolExecutor(max_workers=8) as пул:
    б = list(пул.map(lambda i: вызов("разом #%d" % (i + 1), СИС_ГЕН), range(8)))

print("\n=== Б2. ЕЩЁ ВОСЕМЬ РАЗОМ (кэш уже должен быть тёплым) ===")
with ThreadPoolExecutor(max_workers=8) as пул:
    б2 = list(пул.map(lambda i: вызов("разом2 #%d" % (i + 1), СИС_ГЕН), range(8)))

print("\n=== В. ЧЕРЕДОВАНИЕ ДВУХ ПРЕФИКСОВ ПОДРЯД ===")
в = []
for i in range(3):
    в.append(вызов("ген #%d" % (i + 1), СИС_ГЕН))
    в.append(вызов("вф  #%d" % (i + 1), СИС_ВФ))

print("\n=== Г. РАЗНОЕ УСИЛИЕ НА ОДНОМ ПРЕФИКСЕ ===")
г = [вызов("effort=low", СИС_ГЕН, "low"),
     вызов("effort=medium", СИС_ГЕН, "medium"),
     вызов("effort=low снова", СИС_ГЕН, "low")]


def итог(имя, знач):
    было = [з for з in знач if з >= 0]
    прочли = sum(1 for з in было if з > 0)
    print("  %-34s прочитали кэш %d из %d" % (имя, прочли, len(было)))


print("\n=== ИТОГ ===")
итог("А подряд", а)
итог("Б разом (первая волна)", б)
итог("Б2 разом (вторая волна)", б2)
итог("В чередование", в)
итог("Г разное усилие", г)
