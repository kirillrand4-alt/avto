# -*- coding: utf-8 -*-
"""Сколько вызовов срывается в рассуждение — по усилию и модели.

Партийный генератор с 17.08 ходит на effort=low: на medium шесть вызовов из
восьми уходили в срыв (18-19 тысяч токенов выхода и ни знака текста).
Панельный путь — а это перегенерация и кнопка в панели — так и остался на
medium по умолчанию. Перезапись Meyer вышла $0.69 за попытку против $0.12 у
партийной генерации, и это первый подозреваемый.

Считаем по журналу срывов: он пишет КАЖДЫЙ вызов, поэтому знаменатель есть.
"""
import io
import json
import os
from collections import Counter

Ж = os.environ.get("LETTER_SRYV_LOG") or r"C:\sender\_ops\sryvy.jsonl"
if not os.path.exists(Ж):
    print("журнала срывов нет:", Ж)
    raise SystemExit(0)
всего = Counter()
срывов = Counter()
токенов = Counter()
for s in io.open(Ж, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    ключ = f"{z.get('model')} / {z.get('усилие')}"
    всего[ключ] += 1
    токенов[ключ] += int(z.get("вых") or 0)
    if z.get("срыв"):
        срывов[ключ] += 1
print(f"{'модель / усилие':<38} {'вызовов':>8} {'срывов':>7} {'доля':>6} "
      f"{'выход, ср.':>11}")
for к, n in всего.most_common(10):
    с = срывов.get(к, 0)
    print(f"{к:<38} {n:>8} {с:>7} {100.0 * с / n:>5.0f}% "
          f"{токенов[к] / n:>10.0f}")
