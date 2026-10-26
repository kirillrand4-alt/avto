# -*- coding: utf-8 -*-
"""Сумма цены попыток журнала генерации за день: zhurnal_cena.py <журнал> <YYYY-MM-DD>. Только чтение."""
import io, json, sys
n = ok = 0; s = 0.0
for l in io.open(sys.argv[1], encoding="utf-8"):
    try: z = json.loads(l)
    except ValueError: continue
    if str(z.get("день", "")).startswith(sys.argv[2]) and "цена_$" in z:
        n += 1; ok += 1 if z.get("ок") else 0; s += float(z.get("цена_$") or 0)
print("попыток", n, "годных", ok, "цена $%.2f" % s, "за годное $%.3f" % (s / max(ok, 1)))
