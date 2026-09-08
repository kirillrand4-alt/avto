# -*- coding: utf-8 -*-
"""Алтайский край: что по нему УЖЕ есть в моих потоках, с разбивкой по источникам.

Зачем именно так. Владелец спросил «выпиши все источники, которые использовали либо могли
использовать» для задачи «все предприятия Алтайского края с компрессорным оборудованием:
закупки, ТО, проверки, запчасти». Список источников без чисел — это болтовня: у каждого
канала своя отдача, и назвать её можно только замером. Поэтому сперва считаю, СКОЛЬКО
алтайских предприятий уже дал каждый канал, и только потом называю канал в отчёте.

Признак региона — первые две цифры ИНН: 22 — Алтайский край, 04 — Республика Алтай (это
ДРУГОЙ субъект, считаю отдельно, чтобы не смешать).

Контроль обязателен: беру заведомо несуществующий префикс 99 — если по нему что-то
«найдётся», значит фильтр не фильтрует.
"""
import collections
import csv
import io
import json
import os
import re
import urllib.parse

OPS = r'C:\sender\_ops'
PARK = ['park_ingest_3.jsonl', 'park_ingest_3b.jsonl', 'park_ingest_3c.jsonl',
        'park_ingest_3d.jsonl', 'PARK-PLOSHCHADKI-DLYA-PARKA-3S.jsonl',
        'PARK-RTS-PODTV-3S.jsonl']
BAZA = os.path.join(OPS, 'PARK-BAZA-EDINAYA-3S.csv')
TOCHNO = os.path.join(OPS, 'PARK-BAZA-TOCHNO-3S.csv')
SOSEDI = os.path.join(OPS, 'PARK-VYDACHA-PREDPRIYATIYA.csv')

REGIONY = {'22': 'Алтайский край', '04': 'Республика Алтай', '99': 'КОНТРОЛЬ (такого нет)'}


def hozyain(u):
    try:
        h = urllib.parse.urlparse(u).netloc.lower()
    except Exception:  # noqa: BLE001
        return '—'
    return h[4:] if h.startswith('www.') else h


print('### 1. ПАРК МАШИН: факты по регионам, с разбивкой по хостам-источникам\n')
fakty = collections.defaultdict(list)
vsego = 0
for f in PARK:
    put = os.path.join(OPS, f)
    if not os.path.exists(put):
        print('  %-42s ФАЙЛА НЕТ' % f)
        continue
    n = nash = 0
    for s in io.open(put, encoding='utf-8', errors='replace'):
        s = s.strip()
        if not s:
            continue
        try:
            z = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        n += 1
        vsego += 1
        inn = re.sub(r'\D', '', str(z.get('inn') or ''))
        if len(inn) not in (10, 12):
            continue
        pref = inn[:2]
        if pref in REGIONY:
            fakty[pref].append((inn, z, f))
            if pref == '22':
                nash += 1
    print('  %-42s строк %6d, из них Алтайский край %4d' % (f, n, nash))
print('  %-42s строк %6d' % ('ИТОГО', vsego))

for pref, imya in REGIONY.items():
    sp = fakty.get(pref) or []
    inny = {i for i, _, _ in sp}
    print('\n  %s: фактов %d, предприятий (ИНН) %d' % (imya, len(sp), len(inny)))
    if not sp:
        continue
    hosty = collections.Counter()
    for _, z, _f in sp:
        ist = z.get('istochnik') or z.get('istochniki') or z.get('ssylka') or ''
        if isinstance(ist, list):
            ist = ' '.join(str(x) for x in ist)
        for u in re.findall(r'https?://[^\s|,\'"]+', str(ist)):
            hosty[hozyain(u)] += 1
    print('    хосты-источники:')
    for h, c in hosty.most_common(14):
        print('       %-34s %5d' % (h, c))
    mash = collections.Counter((z.get('mashina') or z.get('vid') or z.get('tip') or '')[:44]
                               for _, z, _f in sp)
    print('    что за машина (как записано):')
    for m, c in mash.most_common(10):
        print('       %-46s %4d' % (m or '(не записано)', c))

print('\n### 2. ЕДИНАЯ БАЗА: строки и контакты по Алтайскому краю\n')
for imya, put in (('вся база', BAZA), ('точно доказанное', TOCHNO)):
    if not os.path.exists(put):
        print('  %-20s ФАЙЛА НЕТ: %s' % (imya, put))
        continue
    r = list(csv.DictReader(io.open(put, encoding='utf-8-sig', errors='replace'), delimiter=';'))
    alt = [z for z in r if re.sub(r'\D', '', z.get('inn') or '').startswith('22')]
    inny = {re.sub(r'\D', '', z['inn']) for z in alt}
    s_tel = [z for z in alt if (z.get('nomer') or '').strip()]
    s_fio = [z for z in alt if (z.get('chelovek') or '').strip()]
    lichn = [z for z in alt if 'мобильн' in (z.get('vid_nomera') or '').lower()
             and 'предприят' not in (z.get('vid_nomera') or '').lower()]
    print('  %-20s всего строк %6d · Алтайский край: строк %4d, предприятий %4d, '
          'с номером %4d, с ФИО %4d, мобильных %3d'
          % (imya, len(r), len(alt), len(inny), len(s_tel), len(s_fio), len(lichn)))
    if alt:
        kan = collections.Counter()
        for z in alt:
            for k in (z.get('kanaly') or '').split(' | '):
                if k.strip():
                    kan[k.strip()] += 1
        print('    каналы, давшие алтайские строки:')
        for k, c in kan.most_common(12):
            print('       %-46s %4d' % (k, c))

print('\n### 3. ПАРК СОСЕДЕЙ (их выдача по предприятиям)\n')
if os.path.exists(SOSEDI):
    r = list(csv.DictReader(io.open(SOSEDI, encoding='utf-8-sig', errors='replace'),
                            delimiter=';'))
    if r and len(r[0]) < 2:
        r = list(csv.DictReader(io.open(SOSEDI, encoding='utf-8-sig', errors='replace')))
    alt = [z for z in r if re.sub(r'\D', '', (z.get('inn') or '')).startswith('22')]
    print('  строк всего %d, Алтайский край %d, предприятий %d'
          % (len(r), len(alt), len({re.sub(r'\D', '', z['inn']) for z in alt})))
else:
    print('  файла нет: %s' % SOSEDI)

print('\n### 4. ПОИМЁННО: алтайские предприятия с доказанной машиной (первые 40)\n')
vidno = {}
for _pref, sp in fakty.items():
    if _pref != '22':
        continue
    for inn, z, f in sp:
        v = vidno.setdefault(inn, {'imya': '', 'mash': set(), 'ssylki': set(), 'n': 0})
        v['n'] += 1
        v['imya'] = v['imya'] or (z.get('predpriyatie') or z.get('zakazchik') or '')
        m = z.get('mashina') or z.get('vid') or ''
        if m:
            v['mash'].add(str(m)[:40])
        ist = z.get('istochnik') or z.get('ssylka') or ''
        if isinstance(ist, list):
            ist = ' '.join(str(x) for x in ist)
        for u in re.findall(r'https?://[^\s|,\'"]+', str(ist))[:1]:
            v['ssylki'].add(u)
for inn, v in sorted(vidno.items(), key=lambda x: -x[1]['n'])[:40]:
    print('  %-12s %-44s фактов %3d  %s' % (inn, (v['imya'] or '—')[:44], v['n'],
                                            (', '.join(sorted(v['mash']))[:60])))
    for u in list(v['ssylki'])[:1]:
        print('        %s' % u[:120])
print('\nвсего алтайских ИНН в парке: %d' % len(vidno))
