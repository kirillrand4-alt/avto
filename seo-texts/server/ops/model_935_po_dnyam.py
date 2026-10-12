# -*- coding: utf-8 -*-
"""Какой моделью писалась партия 935 — по дням, из журнала драйвера."""
import io
import json
from collections import defaultdict

по = defaultdict(lambda: defaultdict(lambda: [0, 0, 0.0, 0.0]))
for с in io.open(r"C:\sender\_ops\gen-partiya-935.jsonl", encoding="utf-8",
                 errors="replace"):
    try:
        z = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if z.get("цена_$") is None:
        continue
    день = str(z.get("создана") or z.get("день") or "?")[:10]
    м = str(z.get("модель") or "?")
    з = по[день][м]
    з[0] += 1
    з[1] += 1 if z.get("тело") else 0
    з[2] += float(z.get("цена_$") or 0)
    з[3] += float(z.get("сек") or 0)
print("%-11s %-22s %6s %6s %9s %6s" % ("день", "модель", "попыт", "годн",
                                       "$/годное", "сек"))
for день in sorted(по):
    for м, (n, г, ц, с) in sorted(по[день].items()):
        print("%-11s %-22s %6d %6d %9.3f %6.0f"
              % (день, м[:22], n, г, ц / max(1, г), с / max(1, n)))
print("=== МОДЕЛЬ 935 ===")
