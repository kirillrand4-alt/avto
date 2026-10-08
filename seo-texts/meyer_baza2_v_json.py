# -*- coding: utf-8 -*-
"""Файл 2 Meyer («ЛПР, остальные телефоны»: рабочие без добавочного, сверены 06.10) -> JSON
для заливки как «База 2». Формат – как у Баз 6 и 4 (тот же загрузчик).

Владелец 08.10: «из 2 и 4 базы не взять всё, а взять только полезное», «загрузи 30».
ПОЛЕЗНЫЕ = новые компании, где: номер именно ЛПР (не бухгалтерия/продажи); номер сверен со
страницей и не со стороннего сайта; сегмент по ОСНОВНОМУ ОКВЭД; выручка от 100 млн или
неизвестна. 9 компаний, уже стоящих в панели, – метка «База 2» и новые номера.
Балл – шкала Баз 1/4/6 (файл 2 – брат файла 1: те же роли, сверка, «проверить»).
"""
import collections
import html
import json
import math
import re
import sys

import pandas as pd

VHOD, VYHOD = sys.argv[1], sys.argv[2]
PANEL = sys.argv[3:]
x = pd.ExcelFile(VHOD)
K = x.parse('Компании', dtype=str)
C = x.parse('Контакты', dtype=str)


def s(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return ''
    return html.unescape(str(v)).strip()


def chislo(v):
    try:
        f = float(s(v).replace(' ', '').replace(',', '.'))
        return f if f > 0 else None
    except ValueError:
        return None


def cif(v):
    d = re.sub(r'\D', '', re.split(r'доб', s(v), flags=re.I)[0])
    return d[-10:] if len(d) >= 10 else ''


panel, panel_nomera = {}, collections.defaultdict(set)
for p in PANEL:
    d = json.load(open(p, encoding='utf-8'))
    for c in d['kompanii']:
        panel.setdefault(c['inn'], c)
    for xk in d['kontakty']:
        if cif(xk['value']):
            panel_nomera[cif(xk['value'])].add(xk['inn'])

LPR = {'закупки', 'директор/руководитель', 'производство', 'главный инженер', 'главный технолог', 'технолог',
       'технический директор', 'качество'}
SILNYE = LPR - {'закупки'}
TEH = {'главный инженер', 'технический директор', 'главный технолог', 'технолог', 'производство'}
po = collections.defaultdict(list)
for _, r in C.iterrows():
    po[s(r['ИНН'])].append(r)


def je_lpr(r):
    return s(r['Роль']) in LPR


def sver(r):
    return bool(re.search(r'верно|исправлено', s(r['Сверка'])))


def ball_kontakta(r):
    rol = s(r['Роль'])
    b = 20 if rol in SILNYE else 15 if rol == 'закупки' else 5
    if s(r['ФИО']):
        b += 10
    if sver(r):
        b += 5
    if 'проверить' in s(r['Проверка']):
        b -= 10
    return b


vybor, sliyanie, otsev = [], [], collections.Counter()
for _, c in K.iterrows():
    inn = s(c['ИНН'])
    ks = po.get(inn, [])
    if inn in panel:
        sliyanie.append((c, ks))
        continue
    vyr = chislo(c['Выручка, руб'])
    if not any(je_lpr(r) for r in ks):
        otsev['только бухгалтерия/продажи'] += 1
    elif any('сторон' in s(r['Проверка']) for r in ks):
        otsev['номер со стороннего сайта'] += 1
    elif not any(sver(r) for r in ks):
        otsev['не сверено'] += 1
    elif s(c['Попадание']) != 'основной ОКВЭД':
        otsev['сегмент только по доп. ОКВЭД'] += 1
    elif vyr is not None and vyr < 1e8:
        otsev['выручка меньше 100 млн'] += 1
    else:
        vybor.append((c, ks))
print('отобрано новых %d, в панели (метка и номера) %d; отсев: %s' % (len(vybor), len(sliyanie), dict(otsev)))

# группы: общий номер с другой компанией файла 2 или панели (gid g2-, группы других баз не трогаем)
roditel = {}


def koren(a):
    roditel.setdefault(a, a)
    while roditel[a] != a:
        roditel[a] = roditel[roditel[a]]
        a = roditel[a]
    return a


obshchih = collections.Counter()
po_nomeru = collections.defaultdict(set)
for _, r in C.iterrows():
    if cif(r['Рабочий']):
        po_nomeru[cif(r['Рабочий'])].add(s(r['ИНН']))
for k10, inns in po_nomeru.items():
    vse = sorted(set(inns) | panel_nomera.get(k10, set()))
    if len(vse) > 1:
        for i in vse:
            obshchih[i] += 1
        for i in vse[1:]:
            roditel[koren(i)] = koren(vse[0])
vybrannye = {s(c['ИНН']) for c, _ in vybor}
kf = {s(c['ИНН']): c for _, c in K.iterrows()}
gr = collections.defaultdict(list)
for i in set(roditel):
    gr[koren(i)].append(i)
gruppy = {}
for g, chl in gr.items():
    if len(chl) < 2 or not any(i in vybrannye for i in chl):
        continue
    sp = []
    for i in chl:
        c = kf.get(i)
        sp.append({'inn': i, 'nazvanie': s(c['Название']) if c is not None else panel[i]['predpriyatie'],
                   'region': s(c['Регион']) if c is not None else panel[i]['region'],
                   'segment': s(c['Сегмент']) if c is not None else panel[i]['segment'],
                   'vyruchka_rub': chislo(c['Выручка, руб']) if c is not None else panel[i].get('vyruchka_rub'),
                   'v_vybore': i in vybrannye or i in panel,
                   'svyaz': 'общих номеров на сайтах компаний: %d' % obshchih[i]})
    gruppy['g2-' + min(chl)] = {'nazvanie': '', 'chleny': sorted(sp, key=lambda z: -(z['vyruchka_rub'] or 0))}
gruppa_inn = {ch['inn']: gid for gid, g in gruppy.items() for ch in g['chleny'] if ch['inn'] in vybrannye}
print('групп с отобранными: %d' % len(gruppy))

kompanii, kontakty = [], []
for c, ks in vybor + sliyanie:
    inn = s(c['ИНН'])
    lprs = sorted([r for r in ks if je_lpr(r)], key=ball_kontakta, reverse=True)
    vyr = chislo(c['Выручка, руб'])
    b_vyr = max(0.0, min(40.0, 10 * math.log10(vyr / 1e7))) if vyr else 0.0
    b_pop = 20 if s(c['Попадание']) == 'основной ОКВЭД' else 0
    b_kont = ball_kontakta(lprs[0]) if lprs else 0
    b_esche = min(10, 5 * max(0, len(lprs) - 1))
    segm = [v.strip() for v in s(c['Сегмент']).split('|') if v.strip()]
    b_segm = min(15, 5 * max(0, len(segm) - 1))
    ball = round(b_vyr + b_pop + b_kont + b_esche + b_segm, 1)
    roli = []
    for r in lprs:
        if s(r['Роль']) not in roli:
            roli.append(s(r['Роль']))
    lk = lprs[0] if lprs else None
    lpr_kratko = (' · '.join(v for v in (s(lk['ФИО']), s(lk['Должность']), s(lk['Рабочий'])) if v)
                  + (' (+ ещё %d)' % (len(lprs) - 1) if len(lprs) > 1 else '')) if lk is not None else ''
    osn = s(c['Основной ОКВЭД'])
    dop = [v.strip() for v in s(c['Доп. ОКВЭД']).split(',') if v.strip()]
    god = s(c['Год выручки'])
    kompanii.append({
        'inn': inn, 'sliyanie': inn in panel, 'predpriyatie': s(c['Название']), 'region': s(c['Регион']),
        'sayt': s(c['Сайт']), 'okved': osn, 'okvedy_vse': ' | '.join([osn] + [d for d in dop if d != osn]),
        'opisanie': s(c['Описание']), 'produkciya': '', 'moshchnosti': '',
        'vyruchka_rub': vyr, 'fin_god': god[:-2] if god.endswith('.0') else god,
        'segment': ' | '.join(segm), 'segment_osn': s(c['Сегмент по основному ОКВЭД']), 'popadanie': s(c['Попадание']),
        'v_baze_obzvona': s(c['В какой базе обзвона']),
        'lpr_kratko': lpr_kratko, 'lpr_roli': ', '.join(roli),
        'moy_prioritet': ball, 'prioritet_pochemu': 'выручка %+.0f · попадание %+d · лучший контакт %+d · ещё ЛПР %+d · '
                                                     'сегменты %+d = %.1f' % (b_vyr, b_pop, b_kont, b_esche, b_segm, ball),
        'kachestvo_nomera': 'ЛПР рабочий' if lprs else '',
        'n_phones': len(ks), 'has_phone': int(bool(ks)),
        'n_purchaser': sum(1 for r in lprs if s(r['Роль']) == 'закупки'),
        'n_tech': sum(1 for r in lprs if s(r['Роль']) in TEH), 'lpr_mobilnyy': 0,
        'lpr_s_fio': sum(1 for r in lprs if s(r['ФИО'])), 'bitrix_fajl': '', 'holding': '',
        'holding_gruppa': gruppa_inn.get(inn, ''), 'v_fajlah_meyer': 'файл 2', 'razdel_kc': '',
        'sayt_chey': '', 'otkuda_kompaniya': '',
        'ssylki_na_istochniki': ' | '.join(sorted({s(r['Ссылка на источник']) for r in ks if s(r['Ссылка на источник'])})),
    })
    for r in ks:
        l = je_lpr(r)
        kontakty.append({
            'inn': inn, 'value': s(r['Рабочий']), 'kind': 'phone', 'person': s(r['ФИО']) or None,
            'role': s(r['Роль']), 'position': s(r['Должность']), 'phone_type': 'рабочий',
            'source': ' · '.join(v for v in (s(r['Источник']), s(r['Сверка']), s(r['Проверка']),
                                             'выход на ЛПР через сотрудника' if 'выход на ЛПР' in s(r['Тип контакта']) else '') if v),
            'source_url': s(r['Ссылка на источник']) or None, 'fragment': '',
            'is_purchaser': int(l and s(r['Роль']) == 'закупки'), 'is_tech': int(l and s(r['Роль']) in TEH),
            'has_role': int(l), 'nomer_ne_lichnyy': None if l else (s(r['Роль']) or 'без подписи'),
            'lpr': int(l), 'cifry': cif(r['Рабочий']),
        })
json.dump({'kompanii': kompanii, 'kontakty': kontakty, 'gruppy': gruppy, 'lyudi': [],
           'fajl': '2-meyer-LPR-ostalnye-telefony-0710_1.xlsx', 'baza': 'База 2',
           'baza_opisanie': 'ЛПР с остальными телефонами'},
          open(VYHOD, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
nov = [k for k in kompanii if not k['sliyanie']]
print('компаний %d (новых %d), номеров %d (ЛПР %d)' % (len(kompanii), len(nov), len(kontakty), sum(k['lpr'] for k in kontakty)))
b = sorted((k['moy_prioritet'] for k in nov), reverse=True)
print('балл новых: макс %.1f, медиана %.1f, мин %.1f' % (b[0], b[len(b) // 2], b[-1]))
print('роли:', collections.Counter(r for k in nov for r in k['lpr_roli'].split(', ') if r).most_common())
