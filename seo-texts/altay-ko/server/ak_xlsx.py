# -*- coding: utf-8 -*-
"""Промежуточная выгрузка в Excel: Предприятия, Карточки доказательств, Финансы, Спорное + Сводка.
По умолчанию в основные листы идёт ТОЛЬКО воздушное компрессорное оборудование (fakty.vozduh=1),
мусор (холод, газ, авто, медтехника) отбрасывается, спорное выносится на отдельный лист.
argv: [FAKTY] - только предприятия с карточками; [FULL] - с кандидатами; [VSE] - не фильтровать по воздуху."""
import os, sys, re, json, sqlite3, collections, time, urllib.request
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite'); OUT = os.path.join(AK, 'AK-FAKTY.xlsx' if 'FAKTY' in sys.argv else 'AK-ITOG.xlsx')
FULL = 'FULL' in sys.argv
TOLKO_VOZDUH = 'VSE' not in sys.argv   # мусор не воздушного КО в выгрузку не идёт
TOLKO_FAKTY = 'FAKTY' in sys.argv   # только предприятия, у которых есть хотя бы одна карточка доказательства
c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True); c.row_factory = sqlite3.Row
SLAB = ('холодильный компрессор', 'ОПО (иное)')
fakty = collections.defaultdict(list); spornye = []; otbrosheno = collections.Counter()
for r in c.execute('select * from fakty order by sila desc'):
    d = dict(r); v = d.get('vozduh')
    if TOLKO_VOZDUH and v != 1:
        otbrosheno['мусор' if v == 0 else 'спорное'] += 1
        if v is None: spornye.append(d)
        continue
    fakty[d['inn']].append(d)
fin = collections.defaultdict(list)
for r in c.execute('select * from finansy'):
    fin[r['inn']].append(dict(r))
PRIOR_V = ['girbo', 'fns-revexp', 'checko', 'checko(requisites)', 'checko(finansy)', 'checko(park-2s)', 'obzvon', 'enrich.companies', 'master']
def luchshee(inn):
    rows = fin.get(inn, []); vyr = prib = nal = ssch = None
    for src in PRIOR_V:
        k = [x for x in rows if x['istochnik'] == src and (x['vyruchka_rub'] or 0) > 0]
        if k: k.sort(key=lambda x: x['fin_god'] or '', reverse=True); vyr = k[0]; break
    for src in ['girbo', 'fns-revexp', 'checko', 'checko(requisites)', 'obzvon']:
        k = [x for x in rows if x['istochnik'] == src and x['pribyl_rub'] is not None]
        if k: k.sort(key=lambda x: x['fin_god'] or '', reverse=True); prib = k[0]; break
    k = [x for x in rows if x['istochnik'] == 'fns-paytax' and x['nalogi_rub']]
    if k: k.sort(key=lambda x: x['fin_god'] or '', reverse=True); nal = k[0]
    k = [x for x in rows if x['ssch']]
    if k: k.sort(key=lambda x: x['fin_god'] or '', reverse=True); ssch = k[0]
    return vyr, prib, nal, ssch
KLASS_ORDER = {'доказано': 0, 'косвенно': 1, 'доказано (слабо)': 2, 'кандидат': 3, 'кандидат (линзы разошлись)': 4, 'кандидат (слабый)': 5, 'без вердикта': 6, 'не оценено': 6, 'не наше': 7}
rows_out = []
# третье условие: эксплуатант ОПО в крае может быть зарегистрирован в другом регионе -
# если по нему есть карточка доказательства, он наш, каким бы ни был ИНН
for r in c.execute("select * from predpriyatiya where inn like '22%' or adres like '%Алтайский край%' or inn in (select distinct inn from fakty)"):
    inn = r['inn']; fs = fakty.get(inn, [])
    silnye = [f for f in fs if (f['sila'] or 0) >= 3 and f['tip'] not in SLAB and f['vid_fakta'] != 'расход газа ЕИС']
    kl = 'доказано' if silnye else ('доказано (слабо)' if fs else (r['klass'] or 'не оценено'))
    if TOLKO_FAKTY and not fs: continue
    if not TOLKO_FAKTY and not FULL and kl in ('не наше', 'не оценено', 'без вердикта'): continue
    if r['status_egrul'] and re.search(r'LIQUIDAT|ликвидир|прекрат', r['status_egrul'], re.I) and not fs: continue
    vyr, prib, nal, ssch = luchshee(inn)
    vidy = collections.Counter(f['vid_fakta'] for f in fs); tipy = collections.Counter(f['tip'] for f in fs if f['tip'])
    marki = sorted({f['marka_model'] for f in fs if f['marka_model']})[:6]
    sroki = sorted({f['srok_do'] for f in fs if f['srok_do']})
    rows_out.append({'inn': inn, 'ogrn': r['ogrn'] or '', 'nazvanie': r['nazvanie'] or r['nazvanie_polnoe'] or '', 'klass': kl,
                     'uverennost': (100 if kl == 'доказано' else (60 if kl == 'доказано (слабо)' else (r['uverennost'] or ''))),
                     'chem_dokazano': '; '.join(f'{k} x{v}' for k, v in vidy.most_common(6)) if fs else (r['tehprocess'] or ''),
                     'tip_mashin': ', '.join(f'{k} x{v}' for k, v in tipy.most_common(6)) if fs else (r['tip_mashin'] or ''),
                     'marki': ' | '.join(marki), 'srok_epb_min': sroki[0] if sroki else '', 'faktov': len(fs),
                     'istochnikov': len({f['istochnik'] for f in fs}), 'istochniki': ' | '.join(sorted({f['istochnik'] for f in fs})),
                     'vyruchka_rub': int(vyr['vyruchka_rub']) if vyr else None, 'god': (vyr['fin_god'] if vyr else ''), 'istochnik_fin': (vyr['istochnik'] if vyr else ''),
                     'pribyl_rub': int(prib['pribyl_rub']) if prib else None, 'nalogi_rub': int(nal['nalogi_rub']) if nal else None,
                     'ssch': (ssch['ssch'] if ssch else (r['ssch'] or None)), 'okved_osn': r['okved_osn'] or '', 'gorod': r['gorod'] or '',
                     'adres': r['adres'] or '', 'sayt': r['sayt'] or '', 'rukovoditel': r['rukovoditel'] or '', 'status': r['status_egrul'] or ''})
rows_out.sort(key=lambda x: (KLASS_ORDER.get(x['klass'], 9), -(x['vyruchka_rub'] or 0), -x['faktov']))
wb = Workbook()
ZAG = PatternFill('solid', fgColor='DDE7F0'); B = Font(bold=True)
def list_(name, kol, dannye, shirina):
    ws = wb.create_sheet(name)
    ws.append(kol)
    for j, cl in enumerate(ws[1], 1): cl.font = B; cl.fill = ZAG; cl.alignment = Alignment(wrap_text=True, vertical='center')
    for d in dannye: ws.append(d)
    for j, w in enumerate(shirina, 1): ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions
    return ws
# лист 1
kol1 = ['№', 'ИНН', 'ОГРН', 'Предприятие', 'Класс', 'Уверенность', 'Чем доказано', 'Типы машин', 'Марки', 'Срок ЭПБ', 'Фактов', 'Источников', 'Источники',
        'Выручка, руб', 'Год', 'Источник финансов', 'Чистая прибыль, руб', 'Налоги уплачено, руб', 'ССЧ', 'ОКВЭД', 'Город', 'Адрес', 'Сайт', 'Руководитель', 'Статус ЕГРЮЛ']
d1 = [[i, x['inn'], x['ogrn'], x['nazvanie'], x['klass'], x['uverennost'], x['chem_dokazano'], x['tip_mashin'], x['marki'], x['srok_epb_min'], x['faktov'], x['istochnikov'], x['istochniki'],
       x['vyruchka_rub'], x['god'], x['istochnik_fin'], x['pribyl_rub'], x['nalogi_rub'], x['ssch'], x['okved_osn'], x['gorod'], x['adres'], x['sayt'], x['rukovoditel'], x['status']]
      for i, x in enumerate(rows_out, 1)]
ws1 = list_('Предприятия', kol1, d1, [5, 12, 14, 42, 16, 11, 34, 26, 22, 11, 8, 11, 26, 16, 7, 16, 16, 16, 8, 12, 16, 44, 22, 26, 18])
for r in ws1.iter_rows(min_row=2, min_col=14, max_col=18):
    for cl in r: cl.number_format = '# ##0'
# лист 2
inns = {x['inn'] for x in rows_out}
kol2 = ['ИНН', 'Предприятие', 'Вид факта', 'Тип машины', 'Марка/модель', 'Дата', 'Срок до', 'Сила', 'Источник', 'Ссылка на первоисточник', 'Цитата', 'Проверка ссылки']
d2 = []
naz = {x['inn']: x['nazvanie'] for x in rows_out}
for inn in inns:
    for f in fakty.get(inn, []):
        d2.append([inn, f['predpriyatie'] or naz.get(inn, ''), f['vid_fakta'], f['tip'], f['marka_model'] or '', f['data'] or '', f['srok_do'] or '', f['sila'],
                   f['istochnik'], f['ssylka'], (f['citata'] or '').replace('\n', ' ')[:900], (f['proverka'] if 'proverka' in f.keys() else '') or ''])
d2.sort(key=lambda x: (x[0], -(x[7] or 0)))
list_('Карточки доказательств', kol2, d2, [12, 40, 20, 22, 18, 11, 11, 6, 18, 60, 90, 20])
# лист 3
kol3 = ['ИНН', 'Предприятие', 'Источник', 'Год', 'Выручка, руб', 'Чистая прибыль, руб', 'Налоги, руб', 'ССЧ']
d3 = []
for inn in inns:
    for x in fin.get(inn, []):
        d3.append([inn, naz.get(inn, ''), x['istochnik'], x['fin_god'], x['vyruchka_rub'], x['pribyl_rub'], x['nalogi_rub'], x['ssch']])
d3.sort(key=lambda x: (x[0], x[2], x[3] or ''))
ws3 = list_('Финансы по источникам', kol3, d3, [12, 40, 20, 7, 16, 18, 16, 8])
for r in ws3.iter_rows(min_row=2, min_col=5, max_col=7):
    for cl in r: cl.number_format = '# ##0'
# лист спорных карточек: слово нашлось, но воздушное ли оборудование - по тексту не видно
if spornye:
    kol4 = ['ИНН', 'Предприятие', 'Вид факта', 'Тип', 'Марка/модель', 'Дата', 'Сила', 'Источник', 'Ссылка', 'Цитата']
    d4 = [[f['inn'], f['predpriyatie'] or naz.get(f['inn'], ''), f['vid_fakta'], f['tip'], f['marka_model'] or '', f['data'] or '',
           f['sila'], f['istochnik'], f['ssylka'], (f['citata'] or '').replace(chr(10), ' ')[:900]] for f in spornye]
    d4.sort(key=lambda x: (x[0], -(x[6] or 0)))
    list_('Спорное (проверить вручную)', kol4, d4, [12, 40, 20, 22, 18, 11, 6, 18, 60, 90])

# лист сводки
sv = wb['Sheet']; sv.title = 'Сводка'
kl_cnt = collections.Counter(x['klass'] for x in rows_out)
ist_cnt = collections.Counter(f['istochnik'] for inn in inns for f in fakty.get(inn, []))
vid_cnt = collections.Counter(f['vid_fakta'] for inn in inns for f in fakty.get(inn, []))
stroki = [['Свод по состоянию на', time.strftime('%Y-%m-%d %H:%M')], [],
          ['Юрлиц Алтайского края в базе (знаменатель)', c.execute("select count(*) from predpriyatiya where inn like '22%' or adres like '%Алтайский край%'").fetchone()[0]],
          ['В этой выгрузке (доказано + косвенно + кандидаты)', len(rows_out)], []]
stroki.append(['По классам', ''])
for k in ['доказано', 'доказано (слабо)', 'косвенно', 'кандидат', 'кандидат (слабый)', 'кандидат (линзы разошлись)']:
    if kl_cnt.get(k): stroki.append([k, kl_cnt[k]])
stroki += [[], ['Карточек доказательств всего (воздушное КО)', len(d2)], ['Предприятий с карточкой', len({x[0] for x in d2})],
           ['Отброшено как не воздушное КО', otbrosheno['мусор']], ['Вынесено в «Спорное»', otbrosheno['спорное']], []]
stroki.append(['Карточки по источникам', ''])
for k, v in ist_cnt.most_common(): stroki.append([k, v])
stroki += [[], ['Карточки по виду факта', '']]
for k, v in vid_cnt.most_common(): stroki.append([k, v])
stroki += [[], ['С выручкой', sum(1 for x in rows_out if x['vyruchka_rub'])], ['С прибылью', sum(1 for x in rows_out if x['pribyl_rub'])],
           ['С налогами', sum(1 for x in rows_out if x['nalogi_rub'])], ['С численностью', sum(1 for x in rows_out if x['ssch'])]]
for s in stroki: sv.append(s)
sv.column_dimensions['A'].width = 46; sv.column_dimensions['B'].width = 18
for cl in sv['A']:
    if cl.value in ('Свод по состоянию на', 'По классам', 'Карточки по источникам', 'Карточки по виду факта'): cl.font = B
c.close()
wb.save(OUT)
print('строк: предприятия', len(rows_out), '| карточки', len(d2), '| финансы', len(d3), '|', os.path.getsize(OUT) // 1024, 'КБ')
data = open(OUT, 'rb').read()
req = urllib.request.Request(os.environ['DROP_URL'].rstrip('/') + '/' + os.path.basename(OUT), data=data, method='PUT', headers={'X-Drop-Token': os.environ['DROP_TOKEN'], 'Content-Type': 'application/octet-stream'})
print('на дроп:', urllib.request.urlopen(req, timeout=600).status)
