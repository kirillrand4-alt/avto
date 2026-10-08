# -*- coding: utf-8 -*-
"""Файл «ЛПР с мобильными и добавочными» -> JSON для заливки в панель Мейера (База 1).

Читается ЛОКАЛЬНО и превращается в простой JSON: на сервере нет гарантии, что в венве
панели есть openpyxl, а JSON читается стандартной библиотекой.

ПРИОРИТЕТ (moy_prioritet). В файле колонки приоритета нет, а балл панели (company_score)
построен под компрессоры: важность покупки, факты о машинах — у мейеровских компаний этих
полей нет, и все получили бы почти одинаковый балл. Поэтому балл считается из того, что
в файле ЕСТЬ, и раскладывается словами в prioritet_pochemu — продавец видит, за что:

  выручка          0..40  — 10 x lg(выручка / 10 млн), в пределах 0..40
  попадание        20     — сегмент по ОСНОВНОМУ ОКВЭД (0, если только по доп.)
  лучший контакт   до 35  — роль: директор/инженер/технолог/производство 20,
                            закупки 15, продажи и сотрудник элеватора 5;
                            +10 за ФИО; +5 «сверено: верно»; −10 «проверить»
  ещё контакты     5 за каждый сверх первого, не больше 10
  сегменты         5 за каждый сверх первого, не больше 15

Поверх панель сама добавит свои надбавки (за телефон, закупщика, техника, раздел ОКВЭД:
пищевое производство +25) — это её общая формула, её не трогаю.
"""
import collections
import json
import math
import re
import sys

from openpyxl import load_workbook

VHOD, VYHOD = sys.argv[1], sys.argv[2]
wb = load_workbook(VHOD, data_only=True)


def list_v_dict(imya):
    rows = list(wb[imya].iter_rows(values_only=True))
    sh = [str(x).strip() for x in rows[0]]
    return [dict(zip(sh, r)) for r in rows[1:] if any(v not in (None, '') for v in r)]


def s(v):
    return '' if v is None else str(v).strip()


def cifry(v):
    c = re.sub(r'\D', '', s(v))
    if len(c) == 11 and c.startswith('8'):
        c = '7' + c[1:]
    return c


komp = list_v_dict('Компании')
kont = list_v_dict('Контакты')

TEH = {'главный инженер', 'технический директор', 'главный технолог', 'технолог', 'производство'}
RUK = {'директор/руководитель'}


def ball_kontakta(k):
    rol = s(k['Роль'])
    b = 20 if (rol in TEH or rol in RUK) else 15 if rol == 'закупки' else 5
    if s(k['ФИО']):
        b += 10
    if 'верно' in s(k['Сверка']) or 'исправлено' in s(k['Сверка']):
        b += 5
    if 'проверить' in s(k['Проверка']):
        b -= 10
    return b


po_inn = collections.defaultdict(list)
for k in kont:
    po_inn[s(k['ИНН'])].append(k)

kompanii, kontakty = [], []
for c in komp:
    inn = s(c['ИНН'])
    ks = sorted(po_inn[inn], key=ball_kontakta, reverse=True)
    vyr = float(c['Выручка, руб']) if c['Выручка, руб'] not in (None, '') else None
    b_vyr = max(0.0, min(40.0, 10 * math.log10(vyr / 1e7))) if vyr and vyr > 0 else 0.0
    b_pop = 20 if s(c['Попадание']) == 'основной ОКВЭД' else 0
    b_kont = ball_kontakta(ks[0]) if ks else 0
    b_esche = min(10, 5 * max(0, len(ks) - 1))
    segm = [x.strip() for x in s(c['Сегмент']).split('|') if x.strip()]
    b_segm = min(15, 5 * max(0, len(segm) - 1))
    ball = round(b_vyr + b_pop + b_kont + b_esche + b_segm, 1)
    pochemu = ('выручка %+.0f · попадание %+d · лучший контакт %+d · ещё контакты %+d · '
               'сегменты %+d = %.1f' % (b_vyr, b_pop, b_kont, b_esche, b_segm, ball))
    luchshiy = ks[0] if ks else {}
    nomer = s(luchshiy.get('Мобильный')) or s(luchshiy.get('Рабочий с добавочным'))
    lpr = ' · '.join(x for x in (s(luchshiy.get('ФИО')), s(luchshiy.get('Должность')), nomer) if x)
    osn = s(c['Основной ОКВЭД'])
    dop = [x.strip() for x in s(c['Доп. ОКВЭД']).split(',') if x.strip()]
    roli = {s(k['Роль']) for k in ks}
    kompanii.append({
        'inn': inn, 'predpriyatie': s(c['Название']), 'region': s(c['Регион']),
        'sayt': s(c['Сайт']), 'okved': osn, 'okvedy_vse': ' | '.join([osn] + dop),
        'opisanie': s(c['Описание']), 'vyruchka_rub': vyr, 'fin_god': s(c['Год выручки']),
        'segment': ' | '.join(segm), 'segment_osn': s(c['Сегмент по основному ОКВЭД']),
        'popadanie': s(c['Попадание']), 'v_baze_obzvona': s(c['В какой базе обзвона']),
        'lpr_kratko': lpr + (' (+ ещё %d)' % (len(ks) - 1) if len(ks) > 1 else ''),
        'moy_prioritet': ball, 'prioritet_pochemu': pochemu,
        'n_phones': len(ks), 'has_phone': int(bool(ks)),
        'n_purchaser': sum(1 for k in ks if s(k['Роль']) == 'закупки'),
        'n_tech': sum(1 for k in ks if s(k['Роль']) in TEH),
        'ssylki_na_istochniki': ' | '.join(sorted({s(k['Ссылка на источник']) for k in ks if s(k['Ссылка на источник'])})),
    })
    for k in ks:
        mob, dob = s(k['Мобильный']), s(k['Рабочий с добавочным'])
        istochnik = ' · '.join(x for x in (s(k['Источник']), s(k['Сверка']), s(k['Проверка']),
                                           'выход на ЛПР через сотрудника' if 'выход на ЛПР' in s(k['Тип контакта']) else '') if x)
        kontakty.append({
            'inn': inn, 'value': mob or dob, 'kind': 'phone',
            'person': s(k['ФИО']) or None, 'role': s(k['Роль']), 'position': s(k['Должность']),
            'phone_type': 'мобильный' if mob else 'рабочий с добавочным',
            'source': istochnik, 'source_url': s(k['Ссылка на источник']) or None,
            'is_purchaser': int(s(k['Роль']) == 'закупки'), 'is_tech': int(s(k['Роль']) in TEH),
            'has_role': 1, 'proverit': int('проверить' in s(k['Проверка'])),
            'tip_kontakta': s(k['Тип контакта']), 'cifry': cifry(mob or dob),
        })

json.dump({'kompanii': kompanii, 'kontakty': kontakty,
           'istochnik_fajla': 'meyer-LPR-mobilnye-i-dobavochnye-0710_2.xlsx'},
          open(VYHOD, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('компаний %d, контактов %d -> %s' % (len(kompanii), len(kontakty), VYHOD))
bally = sorted((k['moy_prioritet'] for k in kompanii), reverse=True)
print('балл: макс %.1f, медиана %.1f, мин %.1f' % (bally[0], bally[len(bally) // 2], bally[-1]))
for k in sorted(kompanii, key=lambda x: -x['moy_prioritet'])[:3] + sorted(kompanii, key=lambda x: x['moy_prioritet'])[:2]:
    print('   %-42s %s' % (k['predpriyatie'][:42], k['prioritet_pochemu']))
