# -*- coding: utf-8 -*-
"""Фаза 2: сопоставление заказчиков из кейсов (projects-index.json) с базой
обзвона (obzvon_all, ИНН/имя/выручка/регион). Стримит 679МБ CSV через stdin —
на диск целиком НЕ кладём. Оставляет только строки базы, чьё норм-имя совпало
с заказчиком кейса. LLM тут НЕ используется (структура, дёшево)."""
import os, re, csv, json, sys
from collections import defaultdict

D = os.path.dirname(os.path.abspath(__file__))
csv.field_size_limit(10 * 1024 * 1024)

OPF = r'(ооо|оао|зао|пао|ао|нао|ип|чоу|чоуо|ано|оано|тд|тпк|нпо|нпп|нпк|гк|фгуп|муп|гуп|фгбу|гбу|мбу|пк|спк|кфх|роо|ассоциация|филиал|представительство|зао|оа|общество|компания|фирма|торговый дом|производственная|научно)'

def norm(name):
    if not name:
        return ''
    s = name.lower().replace('ё', 'е')
    s = re.sub(r'[«»"\'`”“„]', ' ', s)
    s = re.sub(r'\b' + OPF + r'\b', ' ', s)
    s = re.sub(r'[^0-9a-zа-я ]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def is_ip(name):
    return bool(re.match(r'\s*(ип|индивидуальный предприниматель)\b', (name or '').lower()))

# ---- 1. цели из кейсов ----
proj = json.load(open(os.path.join(D, 'projects-index.json'), encoding='utf-8'))
targets = defaultdict(list)   # norm_name -> [row_idx,...]
clients = []                  # исходные заказчики (уникальные)
seen = {}
for r in proj:
    c = (r.get('client') or '').strip()
    if not c:
        continue
    n = norm(c)
    if len(n) < 3:            # слишком короткое/пустое ядро — пропуск
        continue
    if c not in seen:
        seen[c] = len(clients)
        clients.append({'client': c, 'norm': n, 'ip': is_ip(c),
                        'cities': set(), 'proj_count': 0})
    ci = seen[c]
    clients[ci]['cities'].add((r.get('city') or '').strip())
    clients[ci]['proj_count'] += 1
    targets[n].append(ci)

target_norms = set(targets.keys())
sys.stderr.write(f'заказчиков уникальных: {len(clients)}, норм-ключей: {len(target_norms)}\n')
sys.stderr.flush()

# ---- 2. стрим базы обзвона из stdin ----
matches = defaultdict(list)   # ci -> [ {inn,name,revenue,region,baza}, ... ]
rd = csv.reader(sys.stdin, delimiter=';')
header = [h.lstrip('﻿').strip() for h in next(rd)]  # снять BOM
def col(name):
    return header.index(name) if name in header else -1
I_BAZA, I_INN, I_KRAT, I_POLN, I_REG = col('База'), col('ИНН'), col('Краткое'), col('Полное'), col('Регион')
I_REV = col('Выручка, руб.')
rows = 0
for row in rd:
    rows += 1
    if rows % 40000 == 0:
        sys.stderr.write(f'  прочитано строк базы: {rows}\n'); sys.stderr.flush()
    if len(row) <= max(I_BAZA, I_INN, I_KRAT, I_POLN, I_REG, I_REV):
        continue
    for nm in (row[I_KRAT], row[I_POLN]):
        n = norm(nm)
        if n in target_norms:
            rev_raw = (row[I_REV] or '').strip().replace(' ', '').replace('\xa0', '')
            try:
                rev = float(re.sub(r'[^0-9.]', '', rev_raw)) if rev_raw else None
            except ValueError:
                rev = None
            for ci in targets[n]:
                matches[ci].append({
                    'inn': row[I_INN].strip(), 'name': row[I_KRAT].strip(),
                    'revenue': rev, 'region': row[I_REG].strip(),
                    'baza': row[I_BAZA].strip(),
                })
            break

# ---- 3. свод ----
out = []
matched = 0
for ci, c in enumerate(clients):
    ms = matches.get(ci, [])
    # выбираем строку с макс. выручкой (если несколько тёзок)
    best = None
    if ms:
        with_rev = [m for m in ms if m['revenue'] is not None]
        best = max(with_rev, key=lambda m: m['revenue']) if with_rev else ms[0]
        matched += 1
    out.append({
        'client': c['client'], 'norm': c['norm'], 'ip': c['ip'],
        'proj_count': c['proj_count'],
        'cities': sorted(x for x in c['cities'] if x),
        'matched': best is not None,
        'inn': best['inn'] if best else None,
        'revenue': best['revenue'] if best else None,
        'region': best['region'] if best else None,
        'baza': best['baza'] if best else None,
        'n_candidates': len(ms),
    })

json.dump(out, open(os.path.join(D, 'client-revenue-index.json'), 'w'),
          ensure_ascii=False, indent=1)
sys.stderr.write(f'\n=== ГОТОВО ===\nстрок базы прочитано: {rows}\n'
                 f'заказчиков: {len(out)} | сматчилось: {matched} '
                 f'({100*matched//max(1,len(out))}%)\n')
with_rev = [o for o in out if o['revenue']]
sys.stderr.write(f'с выручкой: {len(with_rev)}\n')
