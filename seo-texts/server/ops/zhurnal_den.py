# -*- coding: utf-8 -*-
"""Записи журнала за день: уникальных ИНН, повторы, по часам. Только чтение."""
import io, json, sys
from collections import Counter
зап = []
for l in io.open(sys.argv[1], encoding="utf-8"):
    try: z = json.loads(l)
    except ValueError: continue
    if str(z.get("день", "")).startswith(sys.argv[2]): зап.append(z)
инн = Counter(str(z.get("inn")) for z in зап)
print("записей", len(зап), "уникальных ИНН", len(инн), "самые частые", инн.most_common(3))
print("ключи", sorted(зап[0].keys()) if зап else "")
print("день примеры", Counter(str(z.get("день"))[:13] for z in зап).most_common(30))
