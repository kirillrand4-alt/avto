# -*- coding: utf-8 -*-
r"""Карточку компании собираем от объекта lead, а не от «л».

«л» — словарь, который существует только на публичной странице лида; в
json-ручке панели его нет, и вставка туда молча падала бы в suppress. Объект
lead есть во всех трёх местах, а karta_kompanii принимает и словарь, и объект.
"""
import json
import re

П = r'C:\sender\sender\api\app.py'
with open(П, encoding='utf-8') as f:
    т = f.read()
d = {'было_с_л': т.count('LS.karta_kompanii(getattr(lead, "inn", None), л)')}
т = т.replace('LS.karta_kompanii(getattr(lead, "inn", None), л)',
              'LS.karta_kompanii(getattr(lead, "inn", None), lead)')
with open(П, 'w', encoding='utf-8', newline='') as f:
    f.write(т)
try:
    compile(т, П, 'exec')
    d['синтаксис'] = 'ок'
except SyntaxError as e:
    d['синтаксис'] = str(e)[:150]
d['стало_с_lead'] = т.count('LS.karta_kompanii(getattr(lead, "inn", None), lead)')
d['чистилок_4'] = т.count('LS.bez_citaty, LS.bez_nashey_podpisi)')
print(json.dumps(d, ensure_ascii=False, indent=1))
