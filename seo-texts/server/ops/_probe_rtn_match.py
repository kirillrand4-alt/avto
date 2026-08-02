# -*- coding: utf-8 -*-
"""Сколько строк РТН мы теряем на написании названия, а не на «это не наши».

Сматчено 188 из 3749, остальные помечены «не наши». Но в графике пишут
«ОАО ЧТПЗ», а в ЕГРЮЛ значится «ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО ЧЕЛЯБИНСКИЙ
ТРУБОПРОКАТНЫЙ ЗАВОД» — точное равенство нормализованных строк такое не берёт.
Прежде чем ослаблять правило (а его мы только что ужесточали), надо ЗАМЕРИТЬ,
сколько даст вложение одной строки в другую И СКОЛЬКО ИЗ НИХ БУДУТ
НЕОДНОЗНАЧНЫ. Ничего не пишем.
"""
import io
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\server\ops')
import enrich_db as EDB       # noqa: E402
import rtn_znaniya as RTN     # noqa: E402

П_СТРОКИ = RTN.П_СТРОКИ
ТЕХ = set(EDB.EnrichDB.TECH_ROLES)

e = EDB.EnrichDB().cx
по_ключу = {}
for inn, name in e.execute('SELECT inn,name FROM companies WHERE name IS NOT NULL'):
    к = RTN._норм(name)
    if len(к) >= 4:
        по_ключу.setdefault(к, set()).add(str(inn))
точные = {к: next(iter(s)) for к, s in по_ключу.items() if len(s) == 1}
ключи = list(по_ключу)

итог = Counter()
примеры_влож = []
всего = 0
техн_влож = 0
for ln in io.open(П_СТРОКИ, encoding='utf-8', errors='replace'):
    try:
        d = json.loads(ln)
    except Exception:  # noqa: BLE001
        continue
    for с in (d.get('строки') or []):
        всего += 1
        орг = RTN._норм(с.get('организация'))
        if not орг or len(орг) < 4:
            итог['имя пустое или короткое'] += 1
            continue
        if орг in точные:
            итог['точное совпадение'] += 1
            continue
        if орг in по_ключу:
            итог['точное, но за имя спорят ИНН'] += 1
            continue
        # вложение: одна нормализованная строка целиком внутри другой
        совп = [к for к in ключи if (орг in к or к in орг)]
        инны = set()
        for к in совп:
            инны |= по_ключу[к]
        if not инны:
            итог['не наши совсем'] += 1
        elif len(инны) == 1:
            итог['вложение, ИНН один — можно взять'] += 1
            фио, долж = RTN.починить_отчество(с.get('фио'), с.get('должность'))
            роль = EDB.EnrichDB._canon_role(долж)
            if роль in ТЕХ:
                техн_влож += 1
            if len(примеры_влож) < 12:
                примеры_влож.append({
                    'РТН': (с.get('организация') or '')[:52],
                    'наше': совп[0][:52], 'инн': next(iter(инны)),
                    'должность': долж[:40], 'роль': роль})
        else:
            итог['вложение, но ИНН несколько — нельзя'] += 1

print(json.dumps({
    'строк_всего': всего,
    'разбор': итог.most_common(),
    'технических_среди_однозначных_вложений': техн_влож,
    'примеры': примеры_влож,
}, ensure_ascii=False, indent=1)[:3800])
