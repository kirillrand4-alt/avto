# -*- coding: utf-8 -*-
"""Печать писем чужих моделей из журнала — по именам моделей."""
import io
import json
import re
import sys

ЖУРНАЛ = r"C:\sender\_ops\chuzhie-modeli-pisma.jsonl"
нужны = [a for a in sys.argv[1:]]


def _т(s):
    s = re.sub(r"<br\s*/?>", "\n", str(s or ""), flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n\n", s).strip()


строки = []
for s in io.open(ЖУРНАЛ, encoding="utf-8"):
    try:
        строки.append(json.loads(s))
    except Exception:                                                  # noqa: BLE001
        pass

for z in строки:
    if нужны and z.get("модель") not in нужны:
        continue
    if not z.get("формат_ок"):
        continue
    if "Первый Прокатный" not in str(z.get("фирма")):
        continue          # одна фирма на модель, чтобы влезло в вывод
    print(f"\n{'='*72}")
    print(f"{z['модель']}   ${z['цена_$']}   {z['сек']}с")
    print("=" * 72)
    print(f"ТЕМА: {z.get('тема')}")
    print(_т(z.get("тело")))
