# -*- coding: utf-8 -*-
"""Второй список: предприятия с машиной, куда звонить ЧЕРЕЗ КОММУТАТОР. Правило владельца.

Мой честный вывод прошлых тиков: из 1 185 предприятий с доказанной машиной в список для
звонка попали 111. Остальные 1 074 стоят без единого личного номера, и я перебрала за ночь
шесть каналов — поиск по должности, обратный ход, реестр названий, контактные лица закупок,
B2B, ЭТП ГПБ. Личный номер технического руководителя крупного завода в открытых источниках
лежит редко; это ограничение источников, а не прибора.

Но владелец сказал прямо, и я это перечитала: «неличный номер это путь к человеку через
коммутатор, а выброшенные данные заново не добываются». Значит для этих 1 074 нужен не
личный номер, а ОБЩИЙ — приёмная, 8-800, городской из реквизитов — плюс имя технического
человека, если оно уже найдено без номера. Продавец звонит на коммутатор и просит по имени.

Собираю ровно это, тремя колонками провенанса:
    telefon_obshchiy      + откуда он взят
    chelovek_bez_nomera   + его должность и ссылка, где он назван
    mashina               + ссылка на доказательство машины

ЗАСЛОН: строка идёт в список, только если есть И телефон, И доказательство машины. Имя
человека необязательно — без него звонок всё равно возможен («позовите главного механика»),
но с именем он вдвое короче, поэтому имя тянется, когда оно есть.

Только чтение. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import sqlite3
import urllib.request

PARK = [r'C:\sender\_ops\park_ingest_3.jsonl', r'C:\sender\_ops\park_ingest_3b.jsonl',
        r'C:\sender\_ops\park_ingest_3c.jsonl']
UZHE = r'C:\sender\_ops\PARK-SPISOK-DLYA-ZVONKA-3S.csv'
LYUDI = [r'C:\sender\_ops\PARK-OBRATNYY-STARYY-PROVERENO-3S.jsonl',
         r'C:\sender\_ops\PARK-OBRATNYY-1S-PROVERENO-3S.jsonl',
         r'C:\sender\_ops\PARK-OBRATNYY-2S-PROVERENO-3S.jsonl']
BAZY = [r'C:\sender\enrich.db', r'C:\seostat\data\centrifugal.db',
        r'C:\seostat\drop\drop-storage\atlas_copco.db']
VYHOD = r'C:\sender\_ops\PARK-SPISOK-CHEREZ-KOMMUTATOR-3S.csv'
KLASS = {'ГПА': 5, 'компрессор': 4, 'нагнетатель': 4, 'ВРУ': 4, 'генератор азота': 4,
         'генератор кислорода': 4, 'воздуходувка': 3, 'МКС / передвижная': 3, 'осушитель': 2}
P_INN = re.compile(r'^(inn|company_inn|firma_inn)$', re.I)
P_TEL = re.compile(r'phone|tel|mobil', re.I)


def desyat(t):
    c = re.sub(r'\D', '', str(t or ''))
    if len(c) == 11 and c[0] in '78':
        c = c[1:]
    return c if len(c) == 10 else ''


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
        v = o.get('vid') or 'машина'
        if i not in mash or KLASS.get(v, 0) > KLASS.get(mash[i], 0):
            mash[i] = v
            u = [x for x in (o.get('istochniki') or '').split(' | ') if x.startswith('http')]
            if u:
                mash_ssylka[i] = u[0]

uzhe = set()
if os.path.exists(UZHE):
    for s in io.open(UZHE, encoding='utf-8-sig').read().splitlines()[1:]:
        p_ = s.split(';')
        if p_ and p_[0].strip().isdigit():
            uzhe.add(p_[0].strip())

# люди без номера, найденные обходами
lyudi = collections.defaultdict(list)
for p in LYUDI:
    if not os.path.exists(p):
        continue
    for s in io.open(p, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        if o.get('imya') and o.get('inn'):
            lyudi[o['inn']].append((o['imya'].split(' | ')[0],
                                    (o.get('dolzhnost') or '').split(' | ')[0],
                                    next((x for x in str(o.get('istochniki') or '').split(' | ')
                                          if x.startswith('http')), '')))

imena, tel_obshchiy = {}, {}
for b in BAZY:
    if not os.path.exists(b):
        continue
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % b.replace('\\', '/'), uri=True)
        tabl = [r[0] for r in cx.execute("select name from sqlite_master where type='table'")]
    except Exception:  # noqa: BLE001
        continue
    for t in tabl:
        try:
            kol = [r[1] for r in cx.execute('pragma table_info("%s")' % t)]
        except Exception:  # noqa: BLE001
            continue
        k_inn = [k for k in kol if P_INN.match(k)]
        if not k_inn:
            continue
        pn = next((k for k in ('name', 'naimenovanie', 'company', 'predpriyatie') if k in kol), None)
        k_tel = [k for k in kol if P_TEL.search(k)]
        polya = ([pn] if pn else []) + k_tel
        if not polya:
            continue
        try:
            kur = cx.execute('select %s from "%s"'
                             % (','.join('"%s"' % k for k in k_inn[:1] + polya), t))
        except Exception:  # noqa: BLE001
            continue
        metka = '%s/%s' % (os.path.basename(b), t)
        for r in kur:
            inn = str(r[0] or '').strip()
            if not inn or inn not in mash:
                continue
            j = 1
            if pn:
                v = re.sub(r'\s+', ' ', str(r[1] or '')).strip()
                if len(v) > 4 and inn not in imena:
                    imena[inn] = v
                j = 2
            for v in r[j:]:
                d = desyat(v)
                if d and inn not in tel_obshchiy:
                    tel_obshchiy[inn] = (str(v)[:32], metka)
    cx.close()

spisok, prichiny = [], collections.Counter()
for inn, vid in mash.items():
    if inn in uzhe:
        prichiny['уже в списке с личным номером'] += 1
        continue
    if inn not in tel_obshchiy:
        prichiny['телефона предприятия нет ни в одной базе'] += 1
        continue
    if not mash_ssylka.get(inn):
        prichiny['ссылки на доказательство машины нет'] += 1
        continue
    ch = lyudi.get(inn, [])
    spisok.append({'inn': inn, 'predpriyatie': imena.get(inn, ''),
                   'telefon_obshchiy': tel_obshchiy[inn][0],
                   'telefon_otkuda': tel_obshchiy[inn][1],
                   'chelovek_bez_nomera': ch[0][0] if ch else '',
                   'dolzhnost': ch[0][1] if ch else '',
                   'ssylka_chelovek': ch[0][2] if ch else '',
                   'mashina': vid, 'klass_ceny': KLASS.get(vid, 2),
                   'ssylka_mashina': mash_ssylka[inn]})
spisok.sort(key=lambda o: (-o['klass_ceny'], 0 if o['chelovek_bez_nomera'] else 1))
with io.open(VYHOD, 'w', encoding='utf-8-sig') as f:
    f.write('inn;predpriyatie;telefon_obshchiy;telefon_otkuda;chelovek_bez_nomera;dolzhnost;'
            'mashina;klass_ceny;ssylka_chelovek;ssylka_mashina\n')
    for o in spisok:
        f.write(';'.join(str(o[k]).replace(';', ',') for k in
                         ('inn', 'predpriyatie', 'telefon_obshchiy', 'telefon_otkuda',
                          'chelovek_bez_nomera', 'dolzhnost', 'mashina', 'klass_ceny',
                          'ssylka_chelovek', 'ssylka_mashina')) + '\n')
try:
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    rq = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                           os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT',
                                headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    vyl = op.open(rq, timeout=180).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    vyl = 'не выложено: %s' % str(e)[:80]

s_imenem = [o for o in spisok if o['chelovek_bez_nomera']]
print('\n\n########## ПЕРВЫЕ ДЕСЯТЬ')
for o in spisok[:10]:
    print('  %-12s %-34s %-16s %-24s %s' % (o['inn'], (o['predpriyatie'] or '—')[:34],
                                            o['telefon_obshchiy'][:16],
                                            (o['chelovek_bez_nomera'] or 'имени нет')[:24],
                                            o['mashina'][:14]))
print('\n########## ЧИСЛА')
print('  предприятий с машиной        %5d' % len(mash))
print('  СТРОК В СПИСКЕ               %5d' % len(spisok))
print('  из них с именем человека     %5d  (звонок короче: просят по имени)' % len(s_imenem))
print('  --- по машине')
for k, v in collections.Counter(o['mashina'] for o in spisok).most_common():
    print('     %-26s %5d' % (k, v))
print('  --- не попали')
for k, v in prichiny.most_common():
    print('     %-46s %5d' % (k, v))
print('  файл: %s' % VYHOD)
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'строк': len(spisok), 'с именем': len(s_imenem)},
                           ensure_ascii=False))
