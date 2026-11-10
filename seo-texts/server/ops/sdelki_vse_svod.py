# -*- coding: utf-8 -*-
"""Свод sdelki-vse-1410.json (ИНН → [[направление, статус, дата1, дата2]]): сделки по направлениям и статусам,
провалы Meyer по годам. Только чтение."""
import io, json
from collections import Counter
д = json.load(io.open(r"C:\seostat\drop\drop-storage\sdelki-vse-1410.json", encoding="utf-8"))
сч, год, инн = Counter(), Counter(), Counter()
for ин, сп in д.items():
    for x in сп:
        сч[(x[0], x[1])] += 1
        if x[0] == "meyer" and x[1] == "Провалена": год[str(x[3])[:4]] += 1; инн[ин] += 1
print("ИНН:", len(д)); print("сделки (направление, статус):", sorted(сч.items(), key=lambda kv: (kv[0][0], -kv[1])))
print("провалы Meyer по году закрытия:", sorted(год.items())); print("компаний с провалом Meyer:", len(инн))
