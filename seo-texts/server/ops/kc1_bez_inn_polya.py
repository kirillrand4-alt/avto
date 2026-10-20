# -*- coding: utf-8 -*-
"""Что есть в файле КЦ-1 у компаний без ИНН: заполненность полей и примеры."""
import io
import json
from collections import Counter
лес = json.load(io.open(r"C:\seostat\drop\drop-storage\kc1-lesenka.json", encoding="utf-8"))
гл = [z for z in лес["главные"] if not z.get("inn")]
print("без ИНН в файле:", len(гл))
print({k: sum(1 for z in гл if z.get(k)) for k in гл[0]})
for z in гл[:5]:
    print({k: (str(v)[:50] if v else v) for k, v in z.items()})
