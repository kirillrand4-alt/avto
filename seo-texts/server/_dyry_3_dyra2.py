# -*- coding: utf-8 -*-
"""ДЫРА 2: паспорт в site_facts ЕСТЬ, но пустой, а note пустой.

Ищем сами (не по чужому числу), классифицируем и смотрим, что было на входе.
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

BD = 'file:C:/sender/enrich.db?mode=ro'
KESH = r'C:\seostat\drop\pagecache'

c = sqlite3.connect(BD, uri=True, timeout=30)
c.row_factory = sqlite3.Row

# полезность паспорта: сколько непустых значений в карточке
SLUZH = {'разбор_КЦ', 'источники', 'свежая_новость'}


def nepusto(v):
    if v in (None, '', [], {}):
        return False
    if isinstance(v, str) and not v.strip():
        return False
    return True


vedra = {}
pustye = []
for r in c.execute(
        "select inn, coalesce(facts_json,'') fj, coalesce(note,'') note, "
        "coalesce(popytok,0) pop, coalesce(format,0) fmt, coalesce(otlozheno_do,0) otl, "
        "coalesce(pererazborov,0) per, coalesce(ts,'') ts, coalesce(site,'') site, "
        "coalesce(otkloneno_json,'') otk, coalesce(privyazka,'') priv, "
        "coalesce(sources_json,'') src from site_facts"):
    fj = r['fj']
    if not fj.strip():
        v = 'facts_json пуст (карточки нет)'
        polezno = -1
    else:
        try:
            d = json.loads(fj)
        except Exception:  # noqa: BLE001
            v = 'facts_json не парсится'
            polezno = -2
            d = {}
        else:
            polezno = sum(1 for k, x in d.items() if k not in SLUZH and nepusto(x))
            v = ('карточка ПУСТАЯ (0 непустых полей)' if polezno == 0
                 else 'карточка с содержимым')
    vedra[v] = vedra.get(v, 0) + 1
    if polezno == 0 or (polezno == -1 and not r['note']):
        pustye.append({'inn': str(r['inn']), 'fj': fj[:400], 'note': r['note'],
                       'pop': r['pop'], 'fmt': r['fmt'], 'otl': r['otl'],
                       'per': r['per'], 'ts': r['ts'], 'site': r['site'],
                       'otk_len': len(r['otk']), 'priv': r['priv'],
                       'src_len': len(r['src']), 'polezno': polezno})
print('ВЕДРА site_facts:', json.dumps(vedra, ensure_ascii=False))
print('пустых карточек всего:', len(pustye))
po_note = {}
for p in pustye:
    k = (p['note'][:40] or '(note пуст)')
    po_note[k] = po_note.get(k, 0) + 1
print('по note:', json.dumps(po_note, ensure_ascii=False)[:1200])

# --- только те, где note пуст: это и есть дыра 2 ---
celi = [p for p in pustye if not p['note']]
print('пустая карточка + пустой note:', len(celi))

komp = {}
for r in c.execute("select inn, coalesce(name,'') n, coalesce(site,'') s, "
                   "coalesce(cand_site,'') cs, coalesce(verified,'') v, "
                   "coalesce(site_source,'') ss from companies"):
    komp[str(r[0])] = (r['n'], r['s'], r['cs'], r['v'], r['ss'])
c.close()


def dom(u):
    m = re.match(r'https?://([^/]+)', u or '')
    d = (m.group(1) if m else (u or '')).lower()
    return d[4:] if d.startswith('www.') else d.split('/')[0]


import site_facts as SF  # noqa: E402

KIR = re.compile(r'[а-яё]', re.I)
znakov = []
for p in celi:
    inn = p['inn']
    n, s, cs, v, ss = komp.get(inn, ('', '', '', '', ''))
    p['name'], p['komp_site'], p['cand'], p['verified'], p['site_source'] = n[:60], s, cs, v, ss
    fp = os.path.join(KESH, inn + '.json.gz')
    p['kesh_est'] = os.path.exists(fp)
    if not p['kesh_est']:
        p['klass'] = 'кэша нет'
        continue
    try:
        with gzip.open(fp, 'rb') as f:
            j = json.loads(f.read().decode('utf-8', 'replace'))
    except Exception as e:  # noqa: BLE001
        p['klass'] = 'кэш не читается: ' + str(e)[:60]
        continue
    txt = j.get('text') or ''
    pages = j.get('pages') or []
    p['stranic'] = len(pages)
    p['znakov_text'] = len(txt)
    p['kesh_site'] = (j.get('site') or '')[:80]
    p['kesh_ts'] = j.get('ts', '')
    znakov.append(len(txt))
    # что реально получил бы разбор
    try:
        st = SF._stranicy(inn)
    except Exception:  # noqa: BLE001
        st = []
    p['stranic_v_razbore'] = len(st)
    p['znakov_v_razbore'] = sum(len(t) for _u, t in st)
    obr = ' '.join(t for _u, t in st)[:60000]
    kir = len(KIR.findall(obr))
    p['dolya_kirillicy'] = round(kir / max(1, len(obr)), 3)
    p['dom_kesha'] = dom(j.get('site') or '')
    p['dom_komp'] = dom(s or cs)
    p['chuzhoy_domen'] = bool(p['dom_kesha'] and p['dom_komp']
                              and p['dom_kesha'] != p['dom_komp'])
    p['obrazec'] = re.sub(r'\s+', ' ', obr[:300])
    low = obr.lower()
    p['marker_magazin'] = sum(low.count(w) for w in ('корзина', 'в корзину', 'купить',
                                                     'артикул', 'товаров', 'каталог'))
    p['marker_zaglushka'] = any(w in low for w in (
        'домен продаётся', 'домен продается', 'сайт в разработке', 'запрещенных',
        'страница не найдена', '404', 'this domain', 'for sale', 'заблокирован',
        'технические работы'))
    p['urls'] = [ (pg.get('url') or '')[:70] for pg in pages[:6] ]

print('медиана знаков text у целей:', int(statistics.median(znakov)) if znakov else 0)

klassy = {}
for p in celi:
    if p.get('klass'):
        k = p['klass'][:30]
    elif p.get('stranic_v_razbore', 0) == 0:
        k = 'разбору нечего дать: 0 страниц >=200 знаков'
    elif p.get('dolya_kirillicy', 1) < 0.25:
        k = 'текст почти без кириллицы'
    elif p.get('marker_zaglushka'):
        k = 'заглушка/ошибка/домен продаётся'
    elif p.get('chuzhoy_domen'):
        k = 'домен кэша != домен компании'
    elif p.get('marker_magazin', 0) >= 20:
        k = 'магазин/каталог без фактов о производстве'
    else:
        k = 'текст годный — модель вернула пустую карточку'
    p['klass'] = k
    klassy[k] = klassy.get(k, 0) + 1
print('КЛАССЫ:', json.dumps(klassy, ensure_ascii=False))

os.makedirs(r'C:\sender\_tmp', exist_ok=True)
with open(r'C:\sender\_tmp\dyra2.json', 'w', encoding='utf-8') as f:
    json.dump({'vedra': vedra, 'po_note': po_note, 'celi': celi, 'klassy': klassy},
              f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())

celi.sort(key=lambda x: -(x.get('znakov_text') or 0))
print('30 ПРИМЕРОВ:')
for p in celi[:30]:
    print(' ', p['inn'], '|стр', p.get('stranic'), '|зн', p.get('znakov_text'),
          '|кир', p.get('dolya_kirillicy'), '|fmt', p['fmt'], '|per', p['per'],
          '|', p['klass'][:34], '|', (p.get('kesh_site') or '')[:34],
          '|', (p.get('name') or '')[:28], '|', p['fj'][:60].replace('\n', ' '))
