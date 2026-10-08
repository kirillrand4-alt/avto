# -*- coding: utf-8 -*-
"""Файл 4 Meyer («CC: сайты компаний», номера подтверждены на живых сайтах 07.10) ->
JSON для заливки в панель как «База 4». Формат JSON – как у Базы 6 (тот же загрузчик).

Владелец 08.10: «разбери эту таблицу, давай добавим также только лучшие компании отсюда».
ЛУЧШИЕ = компании с номером ЛПР («ЛПР по списку» в листе «Номера»): 32 новых. Компании,
которые уже есть в панели (16, все из Базы 6), не дублируются: метка «База 4» и новые номера
– провенанс накапливается. Крупные без ЛПР не берутся (предложены владельцу отдельно).

Балл – шкала Баз 1 и 6. «Сайт подтверждён» (+5) – если ИНН взят с самого сайта или из
таблицы и стоит на сайте; «по домену из нашей базы» – без надбавки.

Холдинги: общий номер у разных ИНН – внутри файла 4 И с компаниями, уже стоящими в панели
(у одной компании файла 4 два номера совпали с компанией Базы 6): такая группа уходит
продавцу, у которого уже есть её член. gid с приставкой g4-, чтобы не трогать группы Базы 6.
"""
import collections
import html
import json
import math
import re
import sys

import pandas as pd

VHOD, B1, B6, VYHOD = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
x = pd.ExcelFile(VHOD)
K = x.parse('Компании', dtype=str)
N = x.parse('Номера', dtype=str)
L = x.parse('Люди', dtype=str)


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


b1 = json.load(open(B1, encoding='utf-8'))
b6 = json.load(open(B6, encoding='utf-8'))
panel = {c['inn']: c for c in b1['kompanii'] + b6['kompanii']}
panel_nomera = collections.defaultdict(set)
for xk in b1['kontakty'] + b6['kontakty']:
    if cif(xk['value']):
        panel_nomera[cif(xk['value'])].add(xk['inn'])

SILNYE = {'директор/руководитель', 'главный инженер', 'производство', 'качество', 'коммерческий директор',
          'технический директор', 'главный технолог', 'технолог'}
TEH = {'главный инженер', 'технический директор', 'главный технолог', 'технолог', 'производство'}
KOMMUTATOR = {'общий/приёмная'}

nom_po = collections.defaultdict(list)
for _, r in N.iterrows():
    nom_po[s(r['ИНН'])].append(r)
lyudi_po = collections.defaultdict(list)
for _, r in L.iterrows():
    lyudi_po[s(r['ИНН'])].append(r)


def lpr(r):
    return s(r['Тип контакта']) == 'ЛПР по списку'


def rol(r):
    return s(r['Роль (класс)'])


def tip(r):
    t = s(r['Тип номера'])
    return 'мобильный' if t == 'мобильный' else 'рабочий с добавочным' if 'доб' in t else 'рабочий'


def ball_kontakta(r, est_lpr, sayt_ok):
    if lpr(r):
        b = 20 if rol(r) in SILNYE else 15 if rol(r) == 'закупки' else 10
        if s(r['ФИО']):
            b += 10
        b += 5 if tip(r) == 'мобильный' else 3 if tip(r) == 'рабочий с добавочным' else 0
    else:
        b = 5 if (not est_lpr and rol(r) in KOMMUTATOR) else 0
    return b + (5 if sayt_ok else 0)


# ------------------------------------------------------------------ отбор
vybor, sliyanie = [], []
for _, c in K.iterrows():
    inn = s(c['ИНН'])
    ks = nom_po.get(inn, [])
    lprs = [r for r in ks if lpr(r)]
    if inn in panel:
        uroven = 'уже в панели'
    elif lprs:
        uroven = 'ЛПР мобильный' if any(tip(r) == 'мобильный' for r in lprs) else \
            'ЛПР рабочий с добавочным' if any(tip(r) == 'рабочий с добавочным' for r in lprs) else 'ЛПР рабочий'
    else:
        continue
    (sliyanie if inn in panel else vybor).append((c, ks, uroven))
print('отобрано: новых %d, уже в панели (метка и номера) %d' % (len(vybor), len(sliyanie)))
print('   по уровню:', collections.Counter(u for _, _, u in vybor).most_common())

# ------------------------------------------------------------------ группы по общим номерам
roditel = {}


def koren(a):
    roditel.setdefault(a, a)
    while roditel[a] != a:
        roditel[a] = roditel[roditel[a]]
        a = roditel[a]
    return a


obshchih = collections.Counter()
po_nomeru = collections.defaultdict(set)
for _, r in N.iterrows():
    if cif(r['Номер']):
        po_nomeru[cif(r['Номер'])].add(s(r['ИНН']))
for k10, inns in po_nomeru.items():
    vse = set(inns) | panel_nomera.get(k10, set())
    if len(vse) > 1:
        vse = sorted(vse)
        for i in vse:
            obshchih[i] += 1
        for i in vse[1:]:
            roditel[koren(i)] = koren(vse[0])
kompanii_fajla = {s(c['ИНН']): c for _, c in K.iterrows()}
gruppy_vse = collections.defaultdict(list)
for i in set(roditel):
    gruppy_vse[koren(i)].append(i)
vybrannye = {s(c['ИНН']) for c, _, _ in vybor}
gruppy = {}
for g, chleny in gruppy_vse.items():
    if len(chleny) < 2 or not any(i in vybrannye for i in chleny):
        continue
    gid = 'g4-' + min(chleny)
    spisok = []
    for i in chleny:
        if i in kompanii_fajla:
            c = kompanii_fajla[i]
            spisok.append({'inn': i, 'nazvanie': s(c['Название']), 'region': s(c['Регион']),
                           'segment': s(c['Сегмент (по таблице)']), 'vyruchka_rub': chislo(c['Выручка, руб'])})
        else:
            c = panel[i]
            spisok.append({'inn': i, 'nazvanie': c['predpriyatie'], 'region': c['region'],
                           'segment': c['segment'], 'vyruchka_rub': c.get('vyruchka_rub')})
    for ch in spisok:
        ch['v_vybore'] = ch['inn'] in vybrannye or ch['inn'] in panel
        ch['svyaz'] = 'общих номеров с группой: %d' % obshchih[ch['inn']] if obshchih[ch['inn']] else ''
    gruppy[gid] = {'nazvanie': '', 'chleny': sorted(spisok, key=lambda z: -(z['vyruchka_rub'] or 0))}
gruppa_inn = {ch['inn']: gid for gid, g in gruppy.items() for ch in g['chleny'] if ch['inn'] in vybrannye}
print('групп с отобранными: %d %s' % (len(gruppy), [[ch['nazvanie'][:25] for ch in g['chleny']] for g in gruppy.values()]))

# ------------------------------------------------------------------ компании, номера, люди
kompanii, kontakty, lyudi = [], [], []
for c, ks, uroven in vybor + sliyanie:
    inn = s(c['ИНН'])
    otkuda_inn = s(c['Откуда ИНН'])
    sayt_ok = otkuda_inn.startswith('таблица (есть на сайте)') or otkuda_inn.startswith('сайт')
    est_lpr = any(lpr(r) for r in ks)
    lprs = [r for r in ks if lpr(r)]
    vyr = chislo(c['Выручка, руб'])
    b_vyr = max(0.0, min(40.0, 10 * math.log10(vyr / 1e7))) if vyr else 0.0
    otbor = s(c['Отбор'])
    po_osn = 'ОКВЭД + сайт' in otbor or otbor == 'целевая: ОКВЭД'
    b_pop = 20 if po_osn else 0
    luchshiy = max(ks, key=lambda r: ball_kontakta(r, est_lpr, sayt_ok)) if ks else None
    b_kont = ball_kontakta(luchshiy, est_lpr, sayt_ok) if luchshiy is not None else 0
    b_esche = min(10, 5 * max(0, len(lprs) - 1))
    segm_osn = s(c['Сегмент по основному ОКВЭД'])
    segm = segm_osn if segm_osn and '7 доп. ОКВЭД' not in segm_osn else s(c['Сегмент (по таблице)'])
    b_segm = min(15, 5 * max(0, len([v for v in segm.split('|') if v.strip()]) - 1))
    ball = round(b_vyr + b_pop + b_kont + b_esche + b_segm, 1)
    pochemu = 'выручка %+.0f · попадание %+d · лучший контакт %+d · ещё ЛПР %+d · сегменты %+d = %.1f' % (
        b_vyr, b_pop, b_kont, b_esche, b_segm, ball)
    roli = []
    for r in lprs:
        if rol(r) and rol(r) not in roli:
            roli.append(rol(r))
    if lprs:
        lk = max(lprs, key=lambda r: ball_kontakta(r, True, sayt_ok))
        lpr_kratko = ' · '.join(v for v in (s(lk['ФИО']), s(lk['Должность']) or rol(lk), s(lk['Номер'])) if v)
        if len(lprs) > 1:
            lpr_kratko += ' (+ ещё %d)' % (len(lprs) - 1)
    else:
        lpr_kratko = ''
    osn = s(c['Основной ОКВЭД'])
    dop = [v.strip() for v in s(c['Доп. ОКВЭД']).split(',') if v.strip() and v.strip() != 'нет данных']
    kompanii.append({
        'inn': inn, 'sliyanie': inn in panel, 'predpriyatie': s(c['Название']), 'region': s(c['Регион']),
        'sayt': s(c['Сайт']), 'okved': osn, 'okvedy_vse': ' | '.join([osn] + [d for d in dop if d != osn]),
        'opisanie': s(c['Описание (по сайту)']), 'produkciya': s(c['Продукция']), 'moshchnosti': '',
        'vyruchka_rub': vyr, 'fin_god': s(c['Год дохода']),
        'segment': segm, 'segment_osn': segm_osn, 'popadanie': 'основной ОКВЭД' if po_osn else 'только доп. ОКВЭД',
        'v_baze_obzvona': s(c['В нашей базе обзвона']),
        'lpr_kratko': lpr_kratko, 'lpr_roli': ', '.join(roli),
        'moy_prioritet': ball, 'prioritet_pochemu': pochemu, 'kachestvo_nomera': uroven if uroven != 'уже в панели' else '',
        'n_phones': len(ks), 'has_phone': int(bool(ks)),
        'n_purchaser': sum(1 for r in lprs if rol(r) == 'закупки'),
        'n_tech': sum(1 for r in lprs if rol(r) in TEH),
        'lpr_mobilnyy': int(any(tip(r) == 'мобильный' for r in lprs)),
        'lpr_s_fio': sum(1 for r in lprs if s(r['ФИО'])),
        'bitrix_fajl': '', 'holding': '', 'holding_gruppa': gruppa_inn.get(inn, ''),
        'v_fajlah_meyer': 'файл 4', 'razdel_kc': '', 'sayt_chey': otkuda_inn, 'otkuda_kompaniya': s(c['Откуда сайт']),
        'ssylki_na_istochniki': ' | '.join(sorted({s(r['Страница']) for r in ks if s(r['Страница'])})),
    })
    for r in ks:
        je_lpr = lpr(r)
        naverh = je_lpr or (not est_lpr and rol(r) in KOMMUTATOR)
        kontakty.append({
            'inn': inn, 'value': s(r['Номер']), 'kind': 'phone', 'person': s(r['ФИО']) or None,
            'role': rol(r) if je_lpr else ('' if s(r['Тип контакта']) == 'без подписи' else (rol(r) or s(r['Тип контакта']))),
            'position': s(r['Должность']), 'phone_type': tip(r),
            'source': ' · '.join(v for v in ('сайт компании', 'номер на живой странице сайта 07.10',
                                             'был в таблице CC' if s(r['Номер из таблицы CC']) == 'да' else 'найден на сайте сейчас') if v),
            'source_url': s(r['Страница']) or None, 'fragment': s(r['Как стоит на странице'])[:400],
            'is_purchaser': int(je_lpr and rol(r) == 'закупки'), 'is_tech': int(je_lpr and rol(r) in TEH),
            'has_role': int(naverh),
            'nomer_ne_lichnyy': None if naverh else (rol(r) or s(r['Тип контакта']) or 'без подписи'),
            'lpr': int(je_lpr), 'cifry': cif(r['Номер']),
        })
    for p in lyudi_po.get(inn, []):
        tel = [t.strip() for t in s(p['Телефон рядом (таблица)']).split('\n') if t.strip()]
        lyudi.append({'inn': inn, 'person': s(p['ФИО']), 'position': s(p['Должность']),
                      'phone': tel[0] if tel else None,
                      'source': 'ФИО на живой странице сайта; телефон рядом – из таблицы CC%s' % (
                          '' if s(p['Телефон есть на живом сайте']) == 'да' else ', на сайте сейчас его нет'),
                      'source_url': s(p['Страница-источник']) or None})
json.dump({'kompanii': kompanii, 'kontakty': kontakty, 'gruppy': gruppy, 'lyudi': lyudi,
           'fajl': '4-CC-sayty-kompaniy-0710_1.xlsx', 'baza': 'База 4',
           'baza_opisanie': 'Common Crawl'},
          open(VYHOD, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('компаний %d (новых %d, в панели %d), номеров %d (ЛПР %d), людей %d -> %s' % (
    len(kompanii), len(vybor), len(sliyanie), len(kontakty), sum(k['lpr'] for k in kontakty), len(lyudi), VYHOD))
nov = [k for k in kompanii if not k['sliyanie']]
bally = sorted((k['moy_prioritet'] for k in nov), reverse=True)
print('балл новых: макс %.1f, медиана %.1f, мин %.1f' % (bally[0], bally[len(bally) // 2], bally[-1]))
print('по сегментам:', collections.Counter(k['segment'] for k in nov).most_common())
print('ЛПР-роли новых:', collections.Counter(r for k in nov for r in k['lpr_roli'].split(', ') if r).most_common())
print('добавочный, пример:', next((k['value'] for k in kontakty if 'доб' in k['value']), ''))
