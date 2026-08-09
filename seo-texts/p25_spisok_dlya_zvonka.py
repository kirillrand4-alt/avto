# -*- coding: utf-8 -*-
"""СПИСОК ДЛЯ ЗВОНКА — то, ради чего вся смена. Одна строка = один звонок.

Сводка дала 373 полных строки, из них 305 на предприятиях с ДОКАЗАННОЙ машиной. Здесь я
собираю их в вид, пригодный человеку с телефоном: кому звонить, кем он работает, по какому
номеру, про какую машину и куда смотреть, если он спросит «откуда у вас мои данные».

ЧТО ОБЯЗАТЕЛЬНО В КАЖДОЙ СТРОКЕ:
    ссылка на ЧЕЛОВЕКА  — страница, где стоит его имя рядом с номером
    ссылка на МАШИНУ    — заключение ЭПБ либо закупка, где названа его машина
Строка без обеих ссылок в список не идёт: продавцу нечем будет ответить на вопрос об
источнике, а это первое, что спрашивают.

ПОРЯДОК — не алфавитный. Сверху те, у кого машина дороже (ГПА и компрессор), внутри — у кого
больше независимых доказательств. Если обзвон оборвётся на середине, оборваться он должен на
дешёвом.

ЗАСЛОН НА ДУБЛИ: один человек может прийти из двух потоков. Ключ — ИНН плюс десять цифр
номера; ссылки при свёртке накапливаются, а не заменяются.

Только чтение. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import sqlite3
import urllib.request

SVODKA = r'C:\sender\_ops\PARK-SVODKA-CHELOVEK-ROL-NOMER-3S.jsonl'
PARK = [r'C:\sender\_ops\park_ingest_3.jsonl', r'C:\sender\_ops\park_ingest_3b.jsonl',
        r'C:\sender\_ops\park_ingest_3c.jsonl']
BAZY = [r'C:\sender\enrich.db', r'C:\seostat\data\centrifugal.db']
VYHOD = r'C:\sender\_ops\PARK-SPISOK-DLYA-ZVONKA-3S.csv'
KLASS = {'ГПА': 5, 'компрессор': 4, 'нагнетатель': 4, 'ВРУ': 4, 'генератор азота': 4,
         'генератор кислорода': 4, 'воздуходувка': 3, 'МКС / передвижная': 3, 'осушитель': 2}
MUSOR_DOLZH = re.compile(r'^(развернуть|страница|неясно|нет|—|-|\?)$', re.I)

# машина и ссылка на неё
mash, mash_ssylka = {}, {}
for p in PARK:
    if not os.path.exists(p):
        continue
    for s in io.open(p, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        i = o.get('inn')
        if not i:
            continue
        if i not in mash or KLASS.get(o.get('vid', ''), 0) > KLASS.get(mash[i], 0):
            mash[i] = o.get('vid') or 'машина'
            u = [x for x in (o.get('istochniki') or '').split(' | ') if x.startswith('http')]
            if u:
                mash_ssylka[i] = u[0]

imena = {}
for b in BAZY:
    if not os.path.exists(b):
        continue
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % b.replace('\\', '/'), uri=True)
        for t in ('companies', 'company'):
            try:
                for i, n in cx.execute('select inn, name from "%s" where name is not null' % t):
                    i = str(i or '').strip()
                    if i and i not in imena:
                        imena[i] = re.sub(r'\s+', ' ', str(n)).strip()
            except Exception:  # noqa: BLE001
                continue
        cx.close()
    except Exception:  # noqa: BLE001
        pass

svern, snyato = {}, collections.Counter()
for s in io.open(SVODKA, encoding='utf-8'):
    try:
        o = json.loads(s)
    except Exception:  # noqa: BLE001
        continue
    if o.get('ishod') != 'ПОЛНЫЙ':
        continue
    inn, nomer = o.get('inn', ''), re.sub(r'\D', '', o.get('nomer') or '')
    if not inn or len(nomer) != 10:
        snyato['номер не десятизначный'] += 1
        continue
    if not mash.get(inn):
        snyato['машина у предприятия не доказана'] += 1
        continue
    ssylka_chel = next((x for x in str(o.get('istochniki') or '').split(' | ')
                        if x.startswith('http')), '')
    if not ssylka_chel:
        snyato['нет ссылки на человека'] += 1
        continue
    if not mash_ssylka.get(inn):
        snyato['нет ссылки на машину'] += 1
        continue
    dolzh = (o.get('dolzhnost') or '').split(' | ')[0].strip()
    if MUSOR_DOLZH.match(dolzh):
        dolzh = 'должность не подтверждена'
    k = (inn, nomer)
    if k in svern:
        z = svern[k]
        if ssylka_chel not in z['ssylka_chelovek']:
            z['ssylka_chelovek'] += ' | ' + ssylka_chel
            z['dokazatelstv'] += 1
        continue
    svern[k] = {'inn': inn, 'predpriyatie': imena.get(inn, ''),
                'chelovek': (o.get('chelovek') or '').split(' | ')[0].strip(),
                'dolzhnost': dolzh, 'nomer': '+7' + nomer,
                'mashina': mash[inn], 'klass_ceny': KLASS.get(mash[inn], 2),
                'ssylka_chelovek': ssylka_chel, 'ssylka_mashina': mash_ssylka[inn],
                'dokazatelstv': 2}

spisok = sorted(svern.values(), key=lambda o: (-o['klass_ceny'], -o['dokazatelstv']))
with io.open(VYHOD, 'w', encoding='utf-8-sig') as f:
    f.write('inn;predpriyatie;chelovek;dolzhnost;nomer;mashina;klass_ceny;dokazatelstv;'
            'ssylka_chelovek;ssylka_mashina\n')
    for o in spisok:
        f.write(';'.join(str(o[k]).replace(';', ',') for k in
                         ('inn', 'predpriyatie', 'chelovek', 'dolzhnost', 'nomer', 'mashina',
                          'klass_ceny', 'dokazatelstv', 'ssylka_chelovek',
                          'ssylka_mashina')) + '\n')
try:
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    rq = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                           os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT',
                                headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    vyl = op.open(rq, timeout=180).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    vyl = 'не выложено: %s' % str(e)[:80]

print('\n\n########## ПЕРВЫЕ ДЕСЯТЬ СТРОК СПИСКА')
for o in spisok[:10]:
    print('  %-12s %-30s %-26s %-13s %s' % (o['inn'], (o['predpriyatie'] or '—')[:30],
                                            o['chelovek'][:26], o['nomer'], o['mashina'][:16]))
print('\n########## ЧИСЛА')
print('  строк в списке            %5d  (предприятий %d)'
      % (len(spisok), len({o['inn'] for o in spisok})))
print('  --- по машине')
for k, v in collections.Counter(o['mashina'] for o in spisok).most_common():
    print('     %-26s %5d' % (k, v))
print('  должность не подтверждена %5d'
      % sum(1 for o in spisok if o['dolzhnost'] == 'должность не подтверждена'))
print('  --- не попали в список')
for k, v in snyato.most_common():
    print('     %-44s %5d' % (k, v))
print('  файл: %s' % VYHOD)
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'строк': len(spisok),
                            'предприятий': len({o['inn'] for o in spisok})},
                           ensure_ascii=False))
