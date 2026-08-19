# -*- coding: utf-8 -*-
"""Если кэш всё равно не читается — не платить за его ЗАПИСЬ.

Замер 19.08: у opus-4-8 два одинаковых по статике вызова подряд пишут кэш
заново (11 830 и 11 774 токена) и читают три десятка. Запись тарифицируется
по 1.25 ставки, обычный вход - по 1.0. То есть на каждом вызове мы платим
четверть сверху за услугу, которой не пользуемся.

Проверяем прямо: тот же промпт с cache_control и без него. Если без кэша
вход считается как обычный - выключаем кэш для писем и экономим 20% входа
без единого риска для качества.
"""
import sys

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                        # noqa: E402
from sender.ai_letter import gen_prompt, load_facts              # noqa: E402

ПОЛ = {"mode": "GENERIC", "company_name": "ООО «Третий Кузнечный»",
       "activity": "ковка и штамповка", "okved": "25.50", "extra": {}}
факты = load_facts(division="kc")
п = gen_prompt([ПОЛ], факты, "kc", angle_base=3)
с, т = GP.razrezat_promt(п)
ЦЕНА = (5.0, 25.0)


def _цена(u):
    вх = int(getattr(u, "input_tokens", 0) or 0)
    cw = int(getattr(u, "cache_creation_input_tokens", 0) or 0)
    cr = int(getattr(u, "cache_read_input_tokens", 0) or 0)
    вых = int(getattr(u, "output_tokens", 0) or 0)
    ц = (вх + 1.25 * cw + 0.10 * cr) / 1e6 * ЦЕНА[0] + вых / 1e6 * ЦЕНА[1]
    return вх, cw, cr, вых, ц


for метка, кэш in (("с cache_control", True), ("БЕЗ cache_control", False)):
    m = GP._raw_stream([{"role": "user", "content": т}], "claude-opus-4-8",
                       900, thinking=False, effort="low", system=с,
                       cache_system=кэш)
    вх, cw, cr, вых, ц = _цена(getattr(m, "usage", None))
    print(f"{метка:<20} вход {вх:>6} | запись {cw:>6} | чтение {cr:>5} | "
          f"выход {вых:>5} | ${ц:.4f}")
