# -*- coding: utf-8 -*-
"""Извлечь ВСЕ оси сегментации из базы обзвона (стрим 679МБ через stdin) для
персонализации холодных писем. Оси: направление (КЦ/Meyer), категория
оборудования, ОКВЭД-раздел, регион, тир по выручке. Плюс кросс регион×категория.
LLM не используется — чистая агрегация."""
import os, sys, csv, json, re
from collections import Counter, defaultdict

D = os.path.dirname(os.path.abspath(__file__))
csv.field_size_limit(10 * 1024 * 1024)

rd = csv.reader(sys.stdin, delimiter=';')
header = [h.lstrip('﻿').strip() for h in next(rd)]   # снять BOM с первого столбца
def col(n): return header.index(n) if n in header else -1
I_BAZA, I_INN, I_KRAT = col('База'), col('ИНН'), col('Краткое')
I_REG, I_OKVED = col('Регион'), col('ОсновнойОКВЭД')
I_EQ_MAIN = col('Оборудование по основному ОКВЭД')
I_EQ_ALL = col('Все категории оборудования')
I_REV = col('Выручка, руб.')

baza = Counter()
region = Counter()
okved_sec = Counter()          # раздел ОКВЭД (первые 2 цифры)
eq_main = Counter()            # оборудование по основному ОКВЭД
eq_all = Counter()             # все категории оборудования (по | )
rev_tiers = Counter()
region_x_baza = defaultdict(Counter)
eq_x_baza = defaultdict(Counter)
region_eq = defaultdict(Counter)   # регион -> категории оборудования
rows = 0
rev_known = 0

def tier(v):
    if v is None: return 'нет данных'
    if v >= 5e9:  return 'A: >5 млрд'
    if v >= 1e9:  return 'B: 1-5 млрд'
    if v >= 3e8:  return 'C: 300млн-1млрд'
    if v >= 1e8:  return 'D: 100-300 млн'
    if v >= 3e7:  return 'E: 30-100 млн'
    if v >= 1e7:  return 'F: 10-30 млн'
    return 'G: <10 млн'

for row in rd:
    rows += 1
    if len(row) <= max(I_BAZA,I_REG,I_OKVED,I_EQ_MAIN,I_EQ_ALL,I_REV): continue
    b = row[I_BAZA].strip() or '(пусто)'
    r = row[I_REG].strip() or '(пусто)'
    baza[b] += 1
    region[r] += 1
    region_x_baza[r][b] += 1
    ok = row[I_OKVED].strip()
    m = re.match(r'\s*(\d\d)', ok)
    if m: okved_sec[m.group(1)] += 1
    em = row[I_EQ_MAIN].strip()
    if em and em not in ('-',''): eq_main[em] += 1
    ea = row[I_EQ_ALL].strip()
    if ea and ea not in ('-',''):
        for cat in re.split(r'\s*\|\s*', ea):
            cat = cat.strip()
            if cat:
                eq_all[cat] += 1
                eq_x_baza[cat][b] += 1
                region_eq[r][cat] += 1
    rv = (row[I_REV] or '').strip().replace(' ','').replace('\xa0','')
    try:
        val = float(re.sub(r'[^0-9.]','',rv)) if rv else None
    except ValueError:
        val = None
    if val is not None and val > 0: rev_known += 1
    rev_tiers[tier(val if (val and val>0) else None)] += 1

out = {
  'rows': rows, 'rev_known': rev_known,
  'baza': baza.most_common(),
  'okved_sections': okved_sec.most_common(25),
  'equipment_main': eq_main.most_common(40),
  'equipment_all': eq_all.most_common(60),
  'revenue_tiers': rev_tiers.most_common(),
  'region_top': region.most_common(40),
  'region_count_total': len(region),
  'region_x_baza': {r: dict(c) for r,c in list(region_x_baza.items())},
  'eq_x_baza': {k: dict(v) for k,v in eq_x_baza.items()},
}
json.dump(out, open(os.path.join(D,'segments-base.json'),'w'), ensure_ascii=False, indent=1)

# краткий отчёт в stderr
w = sys.stderr.write
w(f"\n=== БАЗА: {rows} компаний, с выручкой: {rev_known} ===\n")
w(f"\nНАПРАВЛЕНИЕ (База):\n")
for k,v in baza.most_common(): w(f"  {v:>7}  {k}\n")
w(f"\nТИРЫ ПО ВЫРУЧКЕ:\n")
for k,v in sorted(rev_tiers.items()): w(f"  {v:>7}  {k}\n")
w(f"\nКАТЕГОРИИ ОБОРУДОВАНИЯ (Все категории, топ-40):\n")
for k,v in eq_all.most_common(40): w(f"  {v:>7}  {k[:55]}\n")
w(f"\nОКВЭД-РАЗДЕЛЫ (топ-20):\n")
for k,v in okved_sec.most_common(20): w(f"  {v:>7}  раздел {k}\n")
w(f"\nРЕГИОНОВ всего: {len(region)}; топ-25:\n")
for k,v in region.most_common(25): w(f"  {v:>7}  {k[:35]}\n")
