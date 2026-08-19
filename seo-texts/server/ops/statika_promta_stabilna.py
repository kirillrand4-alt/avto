# -*- coding: utf-8 -*-
"""Одинакова ли неизменяемая часть промпта между вызовами — побайтово.

Кэш шлюза читается только когда левая часть БАЙТ-В-БАЙТ та же. По журналу
запись выросла в 50 раз, а чтение упало до нуля — значит где-то статика
поехала. Собираем промпты как в бою и сверяем хеши.
"""
import hashlib
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                        # noqa: E402
from sender.ai_letter import (gen_prompt, judge_prompt,          # noqa: E402
                              load_facts, vf_prompt)

def хеш(s):
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()[:12]

ФИРМЫ = [{"mode": "GENERIC", "company_name": f"ООО «Тест {i}»",
          "activity": "мехобработка", "okved": "25.62", "extra": {}}
         for i in range(4)]

print("== gen_prompt: статика по направлениям и сдвигам угла ==")
for напр in ("kc", "meyer"):
    факты = load_facts(division=напр)
    хеши = Counter()
    длины = Counter()
    for i, ф in enumerate(ФИРМЫ):
        п = gen_prompt([ф], факты, напр, angle_base=i)
        с, т = GP.razrezat_promt(п)
        if с is None:
            print(f"  {напр}: РАЗРЕЗА НЕТ — весь промпт уходит в messages, "
                  "кэш не сработает")
            continue
        хеши[хеш(с)] += 1
        длины[len(с)] += 1
    print(f"  {напр}: разных статик {len(хеши)} — {dict(хеши)}")
    print(f"       длины статики: {dict(длины)}")

print("\n== судья (judge_prompt) ==")
слоты = [(0, [{"subject": "Тема А", "body": "Тело А" * 40},
              {"subject": "Тема Б", "body": "Тело Б" * 40}])]
for напр in ("kc", "meyer"):
    п = judge_prompt(слоты, напр)
    с, т = GP.razrezat_promt(п)
    if с is None:
        print(f"  {напр}: РАЗРЕЗА НЕТ (статика короче 2000 знаков) — "
              f"весь промпт {len(п)} знаков идёт без кэша")
    else:
        print(f"  {напр}: статика {len(с)} знаков, хеш {хеш(с)}")

print("\n== верификатор (vf_prompt) ==")
try:
    п = vf_prompt([{"idx": 0, "subject": "Т", "body": "Б" * 200}],
                  [ФИРМЫ[0]], "kc")
    с, т = GP.razrezat_promt(п)
    print(f"  статика: {len(с) if с else 0} знаков"
          + ("" if с else "  — РАЗРЕЗА НЕТ"))
except Exception as ex:                                          # noqa: BLE001
    print("  не собрался:", str(ex)[:100])
