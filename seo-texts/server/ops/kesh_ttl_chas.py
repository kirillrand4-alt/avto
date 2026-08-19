# -*- coding: utf-8 -*-
"""Помогает ли часовой TTL там, где кэш пишется и не читается.

Ответ поддержки 19.08: стандартный TTL 5 минут, продлённый задаётся В
ЗАПРОСЕ как {"type":"ephemeral","ttl":"1h"}. Запись на час стоит 2.0 ставки
против 1.25, чтение те же 0.1. Если чтение заработает - переплата за запись
окупится со второго же вызова.

Три вызова подряд на одинаковой статике, дважды: обычный кэш и часовой.
"""
import os
import sys

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                        # noqa: E402
from sender.ai_letter import gen_prompt, load_facts              # noqa: E402

# РАЗНЫЕ КОМПАНИИ В КАЖДОЙ ГРУППЕ. Первый заход дал в обеих группах числа,
# совпавшие до токена вместе с выходом (402, 408, 467) - шесть независимых
# вызовов так не совпадают. Запросы были побайтно одинаковыми, и шлюз, судя
# по всему, отдал те же ответы. Сравнивать так нельзя.
ГРУППЫ = {
    "": [{"mode": "GENERIC", "company_name": f"ООО «Проба {i}»",
          "activity": "мехобработка", "okved": "25.62", "extra": {}}
         for i in range(1, 4)],
    "1h": [{"mode": "GENERIC", "company_name": f"ООО «Опыт {i}»",
            "activity": "литьё чугуна", "okved": "24.51", "extra": {}}
           for i in range(1, 4)],
}
факты = load_facts(division="kc")
ЦЕНА = (5.0, 25.0)

for метка, ttl in (("обычный (5 минут)", ""), ("часовой", "1h")):
    if ttl:
        os.environ["LETTER_CACHE_TTL"] = ttl
    else:
        os.environ.pop("LETTER_CACHE_TTL", None)
    print(f"\n== {метка} ==")
    итого = 0.0
    for i, r in enumerate(ГРУППЫ[ttl]):
        п = gen_prompt([r], факты, "kc", angle_base=i)
        с, т = GP.razrezat_promt(п)
        m = GP._raw_stream([{"role": "user", "content": т}],
                           "claude-opus-4-8", 700, thinking=False,
                           effort="low", system=с)
        u = getattr(m, "usage", None)
        вх = int(getattr(u, "input_tokens", 0) or 0)
        cw = int(getattr(u, "cache_creation_input_tokens", 0) or 0)
        cr = int(getattr(u, "cache_read_input_tokens", 0) or 0)
        вых = int(getattr(u, "output_tokens", 0) or 0)
        ставка_записи = 2.0 if ttl == "1h" else 1.25
        ц = ((вх + ставка_записи * cw + 0.10 * cr) / 1e6 * ЦЕНА[0]
             + вых / 1e6 * ЦЕНА[1])
        итого += ц
        print(f"  вызов {i + 1}: вход {вх:>5} | запись {cw:>6} | "
              f"чтение {cr:>6} | выход {вых:>5} | ${ц:.4f}")
    print(f"  итого за три вызова: ${итого:.4f}")
