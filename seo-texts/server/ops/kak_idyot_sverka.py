# -*- coding: utf-8 -*-
"""Сколько записей уже в журнале сверки паспортов и что в них."""
import io
import json
import os
import time
from collections import Counter

Ж = r"C:\sender\_ops\sverka-pasporta.jsonl"
if not os.path.exists(Ж):
    print("журнала нет")
    raise SystemExit(0)
st = os.stat(Ж)
строки = [json.loads(s) for s in io.open(Ж, encoding="utf-8") if s.strip()]
print(f"записей: {len(строки)} | изменён {int(time.time() - st.st_mtime)} с назад")
print("вердикты:", dict(Counter(z.get("verdict") for z in строки)))
for z in строки:
    if z.get("verdict") == "подмена":
        print(f"  #{z['id']} к{z['камп']} {str(z['имя'])[:34]:<34} "
              f"ОКВЭД {str(z['оквэд'])[:26]:<26} сайт: {z.get('chem')}")
