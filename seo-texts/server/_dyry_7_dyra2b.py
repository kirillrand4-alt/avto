# -*- coding: utf-8 -*-
"""ДЫРА 2 (строго): паспорт есть, но ни одного ФАКТИЧЕСКОГО поля не заполнено.
Плюс сверка дыры 1: у кого в stage_log только 'обзвон-merge'.
Только чтение.
"""
import gzip
import json
import os
import re
import sqlite3
import statistics
import sys

sys.path.insert(0, r'C:\sender\server')
RO = 'file:C:/sender/enrich.db?mode=ro'
KESH = r'C:\seostat\drop\pagecache'

FAKT = ['продукция', 'упаковка_фасовка', 'сырьё', 'мощности', 'контроль_качества',
        'экспорт', 'оборудование_линии', 'клиенты', 'год_основания',
        'география_поставок', 'масштаб', 'энергохозяйство', 'расширение', 'газы',
        'новости']


def nepusto(v):
    if v in (None, '', [], {}):
        return False
    return not (isinstance(v, str) and not v.strip())


c = sqlite3.connect(RO, uri=True, timeout=30)
c.row_factory = sqlite3.Row
raspr = {}
celi = []
for r in c.execute(
        "select inn, coalesce(facts_json,'') fj, coalesce(note,'') note, "
        "coalesce(popytok,0) pop, coalesce(format,0) fmt, coalesce(otlozheno_do,0) otl, "
        "coalesce(pererazborov,0) per, coalesce(ts,'') ts, coalesce(site,'') site, "
        "coalesce(otkloneno_json,'') otk, coalesce(privyazka,'') priv from site_facts"):
    fj = r['fj']
    if not fj.strip():
        raspr['карточки нет (facts_json пуст)'] = raspr.get('карточки нет (facts_json пуст)', 0) + 1
        continue
    try:
        d = json.loads(fj)
    except Exception:  # noqa: BLE001
        raspr['не парсится'] = raspr.get('не парсится', 0) + 1
        continue
    n = sum(1 for k in FAKT if nepusto(d.get(k)))
    kl = 'фактических полей: %d' % min(n, 5)
    raspr[kl] = raspr.get(kl, 0) + 1
    if n == 0:
        celi.append({'inn': str(r['inn']), 'note': r['note'], 'pop': r['pop'],
                     'fmt': r['fmt'], 'otl': r['otl'], 'per': r['per'], 'ts': r['ts'],
                     'site': r['site'], 'otk_len': len(r['otk']), 'priv': r['priv'],
                     'kluchi': sorted(d.keys())[:20], 'uverennost': d.get('уверенность', ''),
                     'citata': (d.get('цитата') or '')[:120],
                     'fj_len': len(fj), 'fj': fj[:300]})
print('РАСПРЕДЕЛЕНИЕ карточек:', json.dumps(dict(sorted(raspr.items())), ensure_ascii=False))
print('карточка БЕЗ фактических полей:', len(celi))
print(' из них note пуст:', sum(1 for p in celi if not p['note']))
po_note = {}
for p in celi:
    k = p['note'][:45] or '(note пуст)'
    po_note[k] = po_note.get(k, 0) + 1
print(' по note:', json.dumps(po_note, ensure_ascii=False)[:900])

komp = {}
for r in c.execute("select inn, coalesce(name,'') n, coalesce(site,'') s, "
                   "coalesce(cand_site,'') cs, coalesce(verified,'') v from companies"):
    komp[str(r[0])] = (r['n'], r['s'], r['cs'], r['v'])

# --- сверка дыры 1: stage_log только 'обзвон-merge' ---
odna_stadiya = {}
for inn, n, st in c.execute(
        "select inn, count(*), group_concat(distinct stage) from stage_log group by inn"):
    odna_stadiya[str(inn)] = st or ''
c.close()

import site_facts as SF  # noqa: E402

KIR = re.compile(r'[а-яё]', re.I)


def dom(u):
    m = re.match(r'https?://([^/]+)', u or '')
    d = (m.group(1) if m else (u or '')).lower()
    return d[4:] if d.startswith('www.') else d.split('/')[0]


znak = []
for p in celi:
    inn = p['inn']
    n, s, cs, v = komp.get(inn, ('', '', '', ''))
    p['name'], p['komp_site'], p['cand'], p['verified'] = n[:60], s, cs, v
    fp = os.path.join(KESH, inn + '.json.gz')
    if not os.path.exists(fp):
        p['klass'] = 'кэша уже нет'
        continue
    try:
        with gzip.open(fp, 'rb') as f:
            j = json.loads(f.read().decode('utf-8', 'replace'))
    except Exception as e:  # noqa: BLE001
        p['klass'] = 'кэш не читается: ' + str(e)[:50]
        continue
    p['stranic'] = len(j.get('pages') or [])
    p['kesh_site'] = (j.get('site') or '')[:70]
    p['kesh_ts'] = j.get('ts', '')
    p['istochnik_kesha'] = j.get('istochnik', 'enrich')
    st = SF._stranicy(inn)
    p['stranic_v_razbore'] = len(st)
    p['znakov_v_razbore'] = sum(len(t) for _u, t in st)
    znak.append(p['znakov_v_razbore'])
    obr = ' '.join(t for _u, t in st)[:60000]
    p['dolya_kirillicy'] = round(len(KIR.findall(obr)) / max(1, len(obr)), 3)
    p['dom_kesha'], p['dom_komp'] = dom(j.get('site') or ''), dom(s or cs)
    p['chuzhoy_domen'] = bool(p['dom_kesha'] and p['dom_komp'] and p['dom_kesha'] != p['dom_komp'])
    low = obr.lower()
    p['marker_magazin'] = sum(low.count(w) for w in ('корзина', 'купить', 'артикул', 'каталог'))
    p['zaglushka'] = any(w in low for w in ('домен продаётся', 'домен продается',
                                            'сайт в разработке', 'this domain',
                                            'страница не найдена', 'технические работы',
                                            'ведутся работы', 'under construction'))
    p['obrazec'] = re.sub(r'\s+', ' ', obr[:260])

print('медиана знаков (после очистки, как видит разбор):',
      int(statistics.median(znak)) if znak else 0)
klassy = {}
for p in celi:
    if p.get('klass'):
        k = p['klass'][:28]
    elif p.get('stranic_v_razbore', 0) == 0:
        k = '0 страниц >=200 знаков (разбору нечего дать)'
    elif p.get('dolya_kirillicy', 1) < 0.25:
        k = 'текст почти без кириллицы'
    elif p.get('zaglushka'):
        k = 'заглушка/ошибка/стройка'
    elif p.get('chuzhoy_domen'):
        k = 'домен кэша != домен компании'
    elif p.get('marker_magazin', 0) >= 20:
        k = 'магазин/каталог'
    else:
        k = 'текст годный, модель вернула пусто'
    p['klass'] = k
    klassy[k] = klassy.get(k, 0) + 1
print('КЛАССЫ:', json.dumps(klassy, ensure_ascii=False))

# сверка дыры 1
d1 = json.load(open(r'C:\sender\_tmp\dyra1.json', encoding='utf-8'))
stranic = d1['stranic_bez_pasporta']
sfset = set()
c = sqlite3.connect(RO, uri=True, timeout=30)
sfset = {str(r[0]) for r in c.execute('select inn from site_facts')}
c.close()
kesh_inn = [n.split('.')[0] for n in os.listdir(KESH) if n.endswith('.json.gz')]
bez_p = [i for i in kesh_inn if i not in sfset]
tolko_merge = [i for i in bez_p if odna_stadiya.get(i, '') == 'обзвон-merge']
print('кэш без паспорта, у кого в stage_log ТОЛЬКО обзвон-merge:', len(tolko_merge))
print('  из них >=9 страниц:', sum(1 for i in tolko_merge if stranic.get(i, 0) >= 9))
net_st = [i for i in bez_p if i not in odna_stadiya]
print('кэш без паспорта и вовсе без stage_log:', len(net_st))

with open(r'C:\sender\_tmp\dyra2.json', 'w', encoding='utf-8') as f:
    json.dump({'raspr': raspr, 'celi': celi, 'klassy': klassy, 'po_note': po_note,
               'tolko_merge': tolko_merge[:2000]}, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
celi.sort(key=lambda x: -(x.get('znakov_v_razbore') or 0))
print('30 ПРИМЕРОВ (по убыванию текста):')
for p in celi[:30]:
    print(' ', p['inn'], '|стр', p.get('stranic'), '/', p.get('stranic_v_razbore'),
          '|зн', p.get('znakov_v_razbore'), '|кир', p.get('dolya_kirillicy'),
          '|fmt', p['fmt'], '|per', p['per'], '|', p['klass'][:30],
          '|', (p.get('kesh_site') or '')[:30], '|', (p.get('name') or '')[:26])
