# -*- coding: utf-8 -*-
"""На каких моделях шлюза кэш промпта РАБОТАЕТ.

Замер 19.08: на opus-4-8 два одинаковых по статике вызова подряд пишут кэш
заново (18 089 и 18 096 токенов) и читают три десятка. На sonnet-4-6 по
логу шлюза те же токены читаются. Разница в цене вызова - десятикратная:
запись тарифицируется 1.25 ставки, чтение 0.1.

Гоняем по одной паре вызовов на модель: одинаковая статика, разная
переменная часть. Смотрим ЧТЕНИЕ на втором вызове.
"""
import sys

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                        # noqa: E402
from sender.ai_letter import gen_prompt, load_facts              # noqa: E402

МОДЕЛИ = ["claude-opus-4-8", "claude-fable-5", "claude-sonnet-4-6",
          "claude-opus-4-6", "claude-sonnet-5"]
ПОЛ = [{"mode": "GENERIC", "company_name": "ООО «Первый Механический»",
        "activity": "мехобработка", "okved": "25.62", "extra": {}},
       {"mode": "GENERIC", "company_name": "ООО «Второй Литейный»",
        "activity": "литьё чугуна", "okved": "24.51", "extra": {}}]
факты = load_facts(division="kc")

print(f"{'модель':<22} {'вызов':>6} {'вход':>7} {'чтение':>8} {'запись':>8}")
for м in МОДЕЛИ:
    for i, r in enumerate(ПОЛ):
        п = gen_prompt([r], факты, "kc", angle_base=i)
        с, т = GP.razrezat_promt(п)
        try:
            msg = GP._raw_stream([{"role": "user", "content": т}], м, 900,
                                 thinking=False, effort="low", system=с)
        except Exception as ex:                                  # noqa: BLE001
            print(f"{м:<22} {i + 1:>6} — {type(ex).__name__}: {str(ex)[:60]}")
            break
        u = getattr(msg, "usage", None)
        print(f"{м:<22} {i + 1:>6} "
              f"{int(getattr(u, 'input_tokens', 0) or 0):>7} "
              f"{int(getattr(u, 'cache_read_input_tokens', 0) or 0):>8} "
              f"{int(getattr(u, 'cache_creation_input_tokens', 0) or 0):>8}")
