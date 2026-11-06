# -*- coding: utf-8 -*-
"""Листы и шапки xlsx с дропа (скачать в _ops, если нет): drop_xlsx_shapka.py ФАЙЛ.xlsx"""
import io, os, sys, requests, openpyxl
Ф = sys.argv[1]
for line in io.open(r"C:\sender\panel.env", encoding="utf-8", errors="replace").read().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip('"'))
п = os.path.join(r"C:\sender\_ops", Ф)
if not os.path.exists(п):
    р = requests.get(os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/") + "/" + Ф, headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=300)
    р.raise_for_status(); io.open(п, "wb").write(р.content)
wb = openpyxl.load_workbook(п, read_only=True)
for ws in wb.worksheets:
    print(ws.title, ws.max_row, [str(x)[:25] for x in (next(ws.iter_rows(values_only=True)) or [])][:24])
