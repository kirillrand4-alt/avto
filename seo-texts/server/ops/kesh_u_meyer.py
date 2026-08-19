# -*- coding: utf-8 -*-
"""Читается ли кэш на МЕЙЕРОВСКОМ промпте (он длиннее компрессорного).

Замер на партийном пути делался на промпте КЦ: статика 21 327 знаков,
второй вызов прочитал 8853 токена. Скриншот шлюза показывает у писем
запись 18 тысяч и чтение 40 - значит на живом пути что-то иначе.

Два одинаковых по статике вызова подряд, оба через тот же _raw_stream, что
и генерация. Если второй читает - кэш жив, и дело в порядке вызовов
(потоки, чередование направлений). Если пишет снова - дело в самом промпте.
"""
import sys

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                        # noqa: E402
from sender.ai_letter import gen_prompt, load_facts              # noqa: E402

ПОЛ = [{"mode": "GENERIC", "company_name": "ООО «Первый Пищевой»",
        "activity": "переработка зерна", "okved": "10.61", "extra": {}},
       {"mode": "GENERIC", "company_name": "ООО «Второй Рыбный»",
        "activity": "переработка рыбы", "okved": "10.20", "extra": {}}]

for div in ("meyer", "kc"):
    факты = load_facts(division=div)
    print(f"\n== {div} ==")
    for i, r in enumerate(ПОЛ):
        п = gen_prompt([r], факты, div, angle_base=i)
        с, т = GP.razrezat_promt(п)
        m = GP._raw_stream([{"role": "user", "content": т}],
                           "claude-opus-4-8", 1500, thinking=False,
                           effort="low", system=с)
        u = getattr(m, "usage", None)
        print(f"  вызов {i + 1}: статика {len(с or '')} знаков | "
              f"вход {getattr(u, 'input_tokens', 0)} | "
              f"кэш чтение {getattr(u, 'cache_read_input_tokens', 0)} | "
              f"кэш запись {getattr(u, 'cache_creation_input_tokens', 0)} | "
              f"выход {getattr(u, 'output_tokens', 0)}")
