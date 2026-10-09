# -*- coding: utf-8 -*-
"""fixG3: только чтение. Записи справочника Битрикса КЦ (C:\\centro2\\data\\bitrix_kc_inn.json) по списку ИНН –
чтобы раздача замен считалась с тем же признаком «есть сделки в Битриксе», что увидит панель.

    python3 zapusk_na_servere.py fixG3_bitrix.py ИНН,ИНН,...
"""
import io
import json
import sys

b = json.load(io.open(r'C:\centro2\data\bitrix_kc_inn.json', encoding='utf-8'))
print(json.dumps({i: b.get(i) for i in sys.argv[1].split(',')}, ensure_ascii=False))
