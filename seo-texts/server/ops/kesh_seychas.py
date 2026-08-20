# -*- coding: utf-8 -*-
"""Работает ли кэш ПРЯМО СЕЙЧАС — три вызова опуса настоящим промптом письма.

Короткие вызовы линз для этого не годятся: у них статика меньше порога
разреза, большого кэш-блока нет, и по ним не видно ни починки, ни поломки.
Здесь статика письма — 21 тысяча знаков, её видно сразу.
"""
import sys
import time

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                        # noqa: E402
from sender.ai_letter import gen_prompt, load_facts              # noqa: E402

ФИРМЫ = [("ООО «Проба Первая»", "мехобработка", "25.62"),
         ("ООО «Проба Вторая»", "литьё стали", "24.52"),
         ("ООО «Проба Третья»", "ковка", "25.50")]
# Модель — аргументом: проверять надо каждую, кэш у шлюза
# ведёт себя по-разному на разных бэкендах.
МОДЕЛЬ = next((a for a in sys.argv[1:] if not a.isdigit()),
              "claude-opus-4-8")
print("модель:", МОДЕЛЬ)
факты = load_facts(division="kc")
print(f"{'№':>2} {'вход':>7} {'чтение':>9} {'запись':>9} {'выход':>7} "
      f"{'сек':>4}")
чт = зап = 0
for i, (ф, вид, оквэд) in enumerate(ФИРМЫ, 1):
    пол = {"mode": "GENERIC", "company_name": ф, "activity": вид,
           "okved": оквэд, "extra": {}}
    сис, тело = GP.razrezat_promt(gen_prompt([пол], факты, "kc", angle_base=i))
    т0 = time.time()
    m = GP._raw_stream([{"role": "user", "content": тело}],
                       МОДЕЛЬ, 900, thinking=False, effort="low",
                       system=сис)
    u = getattr(m, "usage", None)
    a = int(getattr(u, "cache_read_input_tokens", 0) or 0)
    b = int(getattr(u, "cache_creation_input_tokens", 0) or 0)
    чт += a
    зап += b
    print(f"{i:>2} {int(getattr(u,'input_tokens',0) or 0):>7} {a:>9} {b:>9} "
          f"{int(getattr(u,'output_tokens',0) or 0):>7} "
          f"{time.time()-т0:>4.0f}")
о = чт / max(1, зап)
print(f"\nчтение/запись = {о:.2f}")
print("КЭШ РАБОТАЕТ" if о > 0.5 else
      "КЭШ ПО-ПРЕЖНЕМУ НЕ ЧИТАЕТСЯ — платим 1.25 ставки за запись впустую")
