# -*- coding: utf-8 -*-
"""Цели для поиска ЛПР: предприятия парка, у которых машина доказана, а личного номера НЕТ.

Замер контактов по парку дал ровно ту картину, ради которой всё и делается:

    ИНН парка 439 | контакт хоть какой-то есть у 375 | ЛИЧНЫХ МОБИЛЬНЫХ 350 на 65 ИНН

То есть машина доказана у 439 предприятий, а человек с личным номером найден у 65.
**Разрыв в 374 предприятия и есть работа.** Всё остальное — приёмные, 8-800, почты —
сохранено и никуда не делось, но цель владельца это личный номер ЛПР.

Собираю список целей: ИНН, название (из боевой базы, а не выдуманное), какая машина
доказана и чем. Название нужно поиску: замер прошлой сессии показал, что аббревиатура
губит привязку — 3 доказуемых из 12 против 10 из 12 у полного имени.

Порядок целей: сперва те, у кого машина дороже (ГПА и компрессор), потом остальные, и
внутри — у кого больше ссылок-доказательств. Это не украшение: если прогон не дойдёт до
конца, оборваться он должен на дешёвом, а не на дорогом.

Только чтение. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import sqlite3
import urllib.request

POTOK = r'C:\sender\_ops\park_ingest_3.jsonl'
KONTAKTY = r'C:\sender\_ops\PARK-KONTAKTY-3S.jsonl'
BAZY = [r'C:\sender\enrich.db', r'C:\seostat\drop\drop-storage\atlas_copco.db']
VYHOD = r'C:\sender\_ops\CELI-PARK-3S.csv'
KLASS = {'ГПА': 5, 'компрессор': 4, 'нагнетатель': 4, 'ВРУ': 4, 'генератор азота': 4,
         'генератор кислорода': 4, 'воздуходувка': 3, 'МКС / передвижная': 3, 'осушитель': 2}

park = collections.defaultdict(lambda: {'vid': collections.Counter(), 'url': set(), 'nap': set()})
for s in io.open(POTOK, encoding='utf-8'):
    o = json.loads(s)
    z = park[o['inn']]
    z['vid'][o['vid']] += 1
    z['nap'].add(o['napisanie'].split(' | ')[0])
    z['url'] |= {u for u in o['istochniki'].split(' | ') if u.startswith('http')}

est_lichnyy, est_hot_chto_to = set(), set()
if os.path.exists(KONTAKTY):
    for s in io.open(KONTAKTY, encoding='utf-8'):
        o = json.loads(s)
        est_hot_chto_to.add(o['inn'])
        if o.get('vid_nomera') == 'ЛИЧНЫЙ МОБИЛЬНЫЙ':
            est_lichnyy.add(o['inn'])

imena, sayty = {}, {}
for baza in BAZY:
    if not os.path.exists(baza):
        continue
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % baza.replace('\\', '/'), uri=True)
    except Exception:  # noqa: BLE001
        continue
    for t in ('companies', 'predpriyatiya', 'ob_enrich_companies'):
        try:
            kol = [r[1] for r in cx.execute('pragma table_info("%s")' % t)]
        except Exception:  # noqa: BLE001
            continue
        if 'inn' not in kol:
            continue
        pn = 'name' if 'name' in kol else ('naimenovanie' if 'naimenovanie' in kol else None)
        ps = 'site' if 'site' in kol else ('domain' if 'domain' in kol else None)
        if not pn:
            continue
        q = 'select inn, "%s"%s from "%s"' % (pn, (', "%s"' % ps) if ps else '', t)
        try:
            for r in cx.execute(q):
                inn = str(r[0] or '').strip()
                if inn and r[1] and inn not in imena:
                    imena[inn] = re.sub(r'\s+', ' ', str(r[1])).strip()
                if ps and len(r) > 2 and r[2] and inn not in sayty:
                    sayty[inn] = str(r[2]).strip()
        except Exception:  # noqa: BLE001
            continue
    cx.close()

celi = []
for inn, z in park.items():
    if inn in est_lichnyy:
        continue
    vid = (z['vid'].most_common(1) or [('компрессор', 0)])[0][0]
    celi.append({'inn': inn, 'predpriyatie': imena.get(inn, ''), 'sayt': sayty.get(inn, ''),
                 'mashina': vid, 'obozn': ' | '.join(sorted(z['nap'])[:2]),
                 'klass': KLASS.get(vid, 2), 'ssylok': len(z['url']),
                 'est_drugoy_kontakt': 'да' if inn in est_hot_chto_to else 'нет',
                 'dokazatelstvo': sorted(z['url'])[0] if z['url'] else ''})
celi.sort(key=lambda o: (-o['klass'], -o['ssylok']))
with io.open(VYHOD, 'w', encoding='utf-8-sig') as f:
    f.write('inn;predpriyatie;sayt;mashina;obozn;klass;ssylok;est_drugoy_kontakt;dokazatelstvo\n')
    for o in celi:
        f.write(';'.join(str(o[k]).replace(';', ',') for k in
                         ('inn', 'predpriyatie', 'sayt', 'mashina', 'obozn', 'klass',
                          'ssylok', 'est_drugoy_kontakt', 'dokazatelstvo')) + '\n')

vylozheno = 'не выкладывала'
try:
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                            os.path.basename(VYHOD)),
                                 data=io.open(VYHOD, 'rb').read(), method='PUT',
                                 headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    vylozheno = op.open(req, timeout=180).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    vylozheno = 'не выложено: %s' % str(e)[:90]

bez_imeni = sum(1 for o in celi if not o['predpriyatie'])
print('\n\n########## ПЕРВЫЕ ДЕСЯТЬ ЦЕЛЕЙ')
for o in celi[:10]:
    print('  %-12s %-44s %-12s ссылок %2d  другой контакт: %s'
          % (o['inn'], (o['predpriyatie'] or 'ИМЕНИ НЕТ')[:44], o['mashina'][:12],
             o['ssylok'], o['est_drugoy_kontakt']))
print('\n########## ЧИСЛА')
print('  ИНН парка                     %5d' % len(park))
print('  из них уже с личным номером   %5d' % len(est_lichnyy & set(park)))
print('  ЦЕЛЕЙ (машина есть, лица нет) %5d' % len(celi))
print('  из них без названия в базе    %5d' % bez_imeni)
print('  из них с сайтом               %5d' % sum(1 for o in celi if o['sayt']))
print('  --- по машине')
for k, v in collections.Counter(o['mashina'] for o in celi).most_common():
    print('     %-30s %5d' % (k, v))
print('  файл: %s' % VYHOD)
print('  выложено: %s' % vylozheno)
print('ИТОГ ' + json.dumps({'целей': len(celi), 'без имени': bez_imeni,
                            'уже с личным': len(est_lichnyy & set(park))}, ensure_ascii=False))
