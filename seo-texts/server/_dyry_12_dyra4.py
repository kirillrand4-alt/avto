# -*- coding: utf-8 -*-
"""ДЫРА 4: сайт и контакты есть, а обогащение не начиналось и кэша нет.

Считаем ОТДЕЛЬНО старую часть базы (istochnik_kompanii пуст) и приехавшую
обзвоном — иначе «нет стадии» означает просто «новая компания».
Проверяем, почему не попали в очередь Зенки (той же меркой, что у очереди),
и живы ли сайты (выборка).
Только чтение.
"""
import json
import os
import random
import re
import sqlite3
import sys
import time

sys.path.insert(0, r'C:\sender\server')
os.environ['NO_BROWSER'] = '1'
RO = 'file:C:/sender/enrich.db?mode=ro'
KESH = r'C:\seostat\drop\pagecache'

c = sqlite3.connect(RO, uri=True, timeout=60)
komp = {}
for r in c.execute("select inn, coalesce(name,''), coalesce(site,''), coalesce(cand_site,''), "
                   "coalesce(verified,''), coalesce(istochnik_kompanii,''), "
                   "coalesce(best_email,''), coalesce(phones,''), coalesce(site_source,'') "
                   'from companies'):
    komp[str(r[0])] = tuple(r[1:])
s_email = {str(r[0]) for r in c.execute('select distinct inn from emails')}
s_phone = {str(r[0]) for r in c.execute('select distinct inn from phone_contacts')}
stadii = {}
for inn, st in c.execute('select inn, group_concat(distinct stage) from stage_log group by inn'):
    stadii[str(inn)] = st or ''
negodnye = {r[0]: (r[1], r[2]) for r in c.execute(
    "select domen, coalesce(uroven,''), coalesce(prichina,'') from domeny_negodnye")}
mnogo = {r[0]: r[1] for r in c.execute('select domen, kompaniy from domeny_mnogo_kompaniy')}
prigovor = {}
try:
    for r in c.execute('select * from prigovor_domenov limit 5'):
        pass
    kol = [x[1] for x in c.execute('PRAGMA table_info(prigovor_domenov)')]
    print('prigovor_domenov колонки:', json.dumps(kol, ensure_ascii=False))
    d0 = kol[0]
    for r in c.execute('select "%s", * from prigovor_domenov' % d0):
        prigovor[str(r[0])] = 1
except Exception as e:  # noqa: BLE001
    print('prigovor_domenov:', str(e)[:100])
c.close()

kesh = {n.split('.')[0] for n in os.listdir(KESH) if n.endswith('.json.gz')}


def bez_stadiy(i):
    st = stadii.get(i, '')
    return st in ('', 'обзвон-merge')


celi_vse, celi_staryh = [], []
for i, v in komp.items():
    name, site, cand, ver, ist, bem, phs, ss = v
    if not (site or cand):
        continue
    if i in kesh:
        continue
    if not bez_stadiy(i):
        continue
    est_kontakt = bool(bem) or (i in s_email) or (i in s_phone) or bool(phs)
    if not est_kontakt:
        continue
    celi_vse.append(i)
    if not ist:
        celi_staryh.append(i)
print('С САЙТОМ И КОНТАКТАМИ, БЕЗ КЭША, БЕЗ СТАДИЙ (кроме обзвон-merge):', len(celi_vse))
print('  из них старая часть базы (istochnik_kompanii пуст):', len(celi_staryh))
print('  приехали обзвоном:', len(celi_vse) - len(celi_staryh))

# --- почему не в очереди Зенки: та же мерка ---
import zenno_most as ZM  # noqa: E402
import enrich_contacts as EC  # noqa: E402


def _dom(u):
    m = re.match(r'https?://([^/]+)', u if str(u).startswith('http') else 'http://' + str(u))
    d = (m.group(1) if m else str(u)).lower()
    return d[4:] if d.startswith('www.') else d.split('/')[0]


och = set()
p = os.path.join(ZM.ZENNO, 'ochered.txt')
if os.path.exists(p):
    with open(p, encoding='utf-8', errors='replace') as f:
        for s in f:
            s = s.strip()
            if s:
                och.add(s.split(';')[0].strip())
got = set()
try:
    with os.scandir(ZM.GOTOVO) as it:
        for e in it:
            x = e.name.split('.')[0].split('_')[0]
            if x.isdigit():
                got.add(x)
except OSError:
    pass
print('в очереди Зенки строк:', len(och), '| в gotovo:', len(got))

prich = {}
podrobno = []
for i in celi_staryh:
    name, site, cand, ver, ist, bem, phs, ss = komp[i]
    u = (site or cand).strip()
    d = _dom(u)
    if ver == 'mismatch':
        pr = 'verified=mismatch — очередь его не берёт'
    elif i in och:
        pr = 'уже стоит в очереди Зенки, обхода ждёт'
    elif i in got:
        pr = 'страницы у Зенки в gotovo, ещё не приняты в кэш'
    elif ZM._ploshchadka(u):
        pr = 'мерка площадок: %s' % (ZM._ploshchadka(u) or '')[:24]
    elif not EC._is_own_site('http://' + d):
        pr = 'мерка _is_own_site: чужая площадка/агрегатор'
    elif d in negodnye:
        pr = 'домен в domeny_negodnye: %s' % negodnye[d][0][:20]
    elif d in mnogo:
        pr = 'домен у %d компаний (domeny_mnogo_kompaniy)' % mnogo[d]
    else:
        pr = 'ОЧЕРЕДЬ ЕГО ВОЗЬМЁТ — просто не дошла'
    prich[pr] = prich.get(pr, 0) + 1
    podrobno.append({'inn': i, 'name': name[:50], 'site': site[:44], 'cand': cand[:44],
                     'domen': d, 'verified': ver, 'site_source': ss[:18],
                     'best_email': bem[:40], 'prichina': pr,
                     'stadii': stadii.get(i, '(нет)')[:40]})
print('ПОЧЕМУ НЕ В ОБХОДЕ (старая часть базы):', json.dumps(
    dict(sorted(prich.items(), key=lambda x: -x[1])), ensure_ascii=False)[:1400])

# --- живы ли сайты: выборка ---
random.seed(7)
proba = random.sample(podrobno, min(60, len(podrobno)))
t0 = time.time()
zhiv = {'открылся': 0, 'не открылся': 0}
for r in proba:
    u = r['site'] or r['cand']
    if not u.startswith('http'):
        u = 'http://' + u
    h = ''
    try:
        h = EC._lyogkiy_zahod(u, timeout=8)
    except Exception:  # noqa: BLE001
        h = ''
    r['otkrylsya'] = bool(h)
    r['znakov'] = len(h)
    zhiv['открылся' if h else 'не открылся'] += 1
print('ЖИВОСТЬ САЙТОВ (выборка %d, %.0f сек): %s' % (
    len(proba), time.time() - t0, json.dumps(zhiv, ensure_ascii=False)))
zhiv_po_prich = {}
for r in proba:
    k = r['prichina'][:34]
    a = zhiv_po_prich.setdefault(k, [0, 0])
    a[0] += 1
    a[1] += 1 if r['otkrylsya'] else 0
print('  по причинам (всего/открылось):', json.dumps(zhiv_po_prich, ensure_ascii=False)[:900])

with open(r'C:\sender\_tmp\dyra4.json', 'w', encoding='utf-8') as f:
    json.dump({'vsego': len(celi_vse), 'staryh': len(celi_staryh),
               'prichiny': prich, 'podrobno': podrobno, 'proba_zhivosti': proba,
               'zhiv': zhiv}, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
print('30 ПРИМЕРОВ:')
for r in podrobno[:30]:
    print(' ', r['inn'], '|', r['prichina'][:40], '|', (r['site'] or r['cand'])[:34],
          '|', r['name'][:26], '|', r['best_email'][:26])
