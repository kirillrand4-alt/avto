# -*- coding: utf-8 -*-
"""ДЫРА 3: страницы в кэше есть, контактов в базе нет.

Выемку НЕ переписываем: импортируем из enrich_contacts (_harvest_from_html,
EMAIL_RE, phones_in, _is_junk_email, rol_iz_imeni_yashchika) и гоним ровно то,
что делает crawl_contacts по каждой странице. Только чтение.
"""
import gzip
import json
import os
import random
import re
import sqlite3
import statistics
import sys
import time

sys.path.insert(0, r'C:\sender\server')
os.environ['NO_BROWSER'] = '1'
RO = 'file:C:/sender/enrich.db?mode=ro'
KESH = r'C:\seostat\drop\pagecache'

import enrich_contacts as EC  # noqa: E402

c = sqlite3.connect(RO, uri=True, timeout=30)
s_email = {str(r[0]) for r in c.execute('select distinct inn from emails')}
s_phone = {str(r[0]) for r in c.execute('select distinct inn from phone_contacts')}
s_people = {str(r[0]) for r in c.execute('select distinct inn from people')}
komp = {}
for r in c.execute("select inn, coalesce(name,''), coalesce(site,''), "
                   "coalesce(cand_site,''), coalesce(verified,''), coalesce(ogrn,''), "
                   "coalesce(best_email,''), coalesce(phones,'') from companies"):
    komp[str(r[0])] = tuple(r[1:])
stadii = {}
for inn, st in c.execute('select inn, group_concat(distinct stage) from stage_log group by inn'):
    stadii[str(inn)] = st or ''
# телефоны, уже известные базе — чтобы понять, сколько из добытого «справочник»
tel_vladelcev = {}
for inn, ph in c.execute('select inn, phone from phone_contacts'):
    d = re.sub(r'\D', '', ph or '')[-10:]
    if len(d) == 10:
        tel_vladelcev.setdefault(d, set()).add(str(inn))
c.close()

kesh = [n.split('.')[0] for n in os.listdir(KESH) if n.endswith('.json.gz')]
celi = [i for i in kesh if i not in s_email and i not in s_phone]
s_sajtom = [i for i in celi if i in komp and (komp[i][1] or komp[i][2])]
print('файлов кэша:', len(kesh))
print('кэш есть, но НЕТ ни почт, ни телефонов:', len(celi))
print('  из них с сайтом в companies:', len(s_sajtom))
print('  из них есть в companies:', sum(1 for i in celi if i in komp))
print('  из них ещё и людей нет:', sum(1 for i in celi if i not in s_people))
st_raspr = {}
for i in celi:
    k = stadii.get(i, '(нет стадий)')
    k = ('только обзвон-merge' if k == 'обзвон-merge'
         else ('нет стадий' if k == '(нет стадий)'
               else ('есть crawl' if 'crawl' in k else 'иные стадии без crawl')))
    st_raspr[k] = st_raspr.get(k, 0) + 1
print('  по стадиям:', json.dumps(st_raspr, ensure_ascii=False))

# ---------- выемка по выборке ----------
random.seed(20260824)
vyborka = random.sample(celi, min(260, len(celi)))
t0 = time.time()
itog = []
vse_tel = {}
for k, inn in enumerate(vyborka):
    p = os.path.join(KESH, inn + '.json.gz')
    rec = {'inn': inn, 'name': (komp.get(inn) or ('',))[0][:60],
           'site': (komp.get(inn) or ('', ''))[1] if inn in komp else '',
           'stadii': stadii.get(inn, '')[:60]}
    try:
        with gzip.open(p, 'rb') as f:
            j = json.loads(f.read().decode('utf-8', 'replace'))
    except Exception as e:  # noqa: BLE001
        rec['err'] = str(e)[:60]
        itog.append(rec)
        continue
    pages = j.get('pages') or []
    rec['stranic'] = len(pages)
    rec['kesh_site'] = (j.get('site') or '')[:70]
    rec['istochnik'] = j.get('istochnik', 'enrich')
    pochty, tel = set(), set()
    for pg in pages:
        h = pg.get('html') or ''
        if not h:
            continue
        pe, ph = EC._harvest_from_html(h)
        pt = re.sub(r'<[^>]+>', ' ',
                    re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I))
        for e in EC.EMAIL_RE.findall(pt):
            pe.add(e.lower())
        for m in EC.phones_in(pt):
            ph.add(re.sub(r'\D', '', m.group(0)))
        pochty |= {e for e in pe if not e.endswith(EC._IMG_EXT)}
        tel |= ph
    ogrn = (komp.get(inn) or ('',) * 6)[4] if inn in komp else ''
    chistye = sorted(e for e in pochty if not EC._is_junk_email(e))
    musor_p = sorted(pochty - set(chistye))
    norm = set()
    rekvizit = 0
    for t in tel:
        d = re.sub(r'\D', '', t)
        if len(d) == 11 and d[0] in '78':
            d = d[1:]
        if len(d) != 10:
            continue
        i10 = re.sub(r'\D', '', inn)
        o = re.sub(r'\D', '', str(ogrn))
        if (i10 and d == i10[:10]) or (o and d in o):
            rekvizit += 1
            continue
        norm.add(d)
    for d in norm:
        vse_tel.setdefault(d, set()).add(inn)
    rec['pocht'] = len(chistye)
    rec['pocht_musor'] = len(musor_p)
    rec['pocht_obshchie'] = sum(1 for e in chistye
                                if EC.rol_iz_imeni_yashchika(e) in ('общий', 'приёмная', ''))
    rec['pocht_s_rolyu'] = sum(1 for e in chistye
                               if EC.rol_iz_imeni_yashchika(e) not in ('общий', 'приёмная', ''))
    rec['tel'] = len(norm)
    rec['tel_rekvizit'] = rekvizit
    rec['tel_chuzhie'] = sum(1 for d in norm if d in tel_vladelcev
                             and inn not in tel_vladelcev[d])
    rec['primery_pocht'] = chistye[:6]
    rec['primery_tel'] = sorted(norm)[:6]
    itog.append(rec)
    if k % 50 == 0:
        print('  ...%d/%d %ds' % (k, len(vyborka), time.time() - t0), flush=True)

sek = time.time() - t0
ok = [r for r in itog if 'err' not in r]
s_pocht = [r for r in ok if r['pocht']]
s_tel = [r for r in ok if r['tel']]
vsego_p = sum(r['pocht'] for r in ok)
vsego_t = sum(r['tel'] for r in ok)
print('ВЫБОРКА %d компаний, %.1f сек (%.2f сек/компанию)' % (len(ok), sek, sek / max(1, len(ok))))
print('  с хотя бы одной почтой: %d (%.1f%%)' % (len(s_pocht), 100.0 * len(s_pocht) / max(1, len(ok))))
print('  с хотя бы одним телефоном: %d (%.1f%%)' % (len(s_tel), 100.0 * len(s_tel) / max(1, len(ok))))
print('  всего почт %d (медиана у нашедших %s), телефонов %d (медиана %s)' % (
    vsego_p, int(statistics.median([r['pocht'] for r in s_pocht])) if s_pocht else 0,
    vsego_t, int(statistics.median([r['tel'] for r in s_tel])) if s_tel else 0))
print('  почт-мусора (платформы/noreply, отсеяно _is_junk_email): %d' % sum(r['pocht_musor'] for r in ok))
print('  из чистых почт «общий/не опознан»: %d; с ролью в имени ящика: %d' % (
    sum(r['pocht_obshchie'] for r in ok), sum(r['pocht_s_rolyu'] for r in ok)))
print('  телефонов-реквизитов (ИНН/ОГРН по маске) отброшено: %d' % sum(r['tel_rekvizit'] for r in ok))
print('  телефонов, уже записанных за ДРУГИМ ИНН (коммутатор/справочник): %d' % sum(
    r['tel_chuzhie'] for r in ok))
mnogo = {d: sorted(v) for d, v in vse_tel.items() if len(v) >= 3}
print('  номеров, встретившихся у >=3 компаний ВЫБОРКИ (справочники): %d' % len(mnogo))

n = len(celi)
kp = len(ok)
print('ЭКСТРАПОЛЯЦИЯ на %d компаний: почт ~%d, телефонов ~%d; компаний с контактом ~%d' % (
    n, round(vsego_p * n / max(1, kp)), round(vsego_t * n / max(1, kp)),
    round(len({r['inn'] for r in s_pocht} | {r['inn'] for r in s_tel}) * n / max(1, kp))))
print('ВРЕМЯ полного прогона по %d компаниям: ~%.0f мин в один поток' % (
    n, n * (sek / max(1, kp)) / 60))

with open(r'C:\sender\_tmp\dyra3.json', 'w', encoding='utf-8') as f:
    json.dump({'vsego_celey': n, 's_sajtom': len(s_sajtom), 'stadii': st_raspr,
               'vyborka': itog, 'spravochnye_nomera': mnogo,
               'celi': celi}, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
print('30 ПРИМЕРОВ:')
for r in sorted(ok, key=lambda x: -(x['pocht'] + x['tel']))[:30]:
    print(' ', r['inn'], '|стр', r.get('stranic'), '|почт', r['pocht'], '|тел', r['tel'],
          '|', (r.get('kesh_site') or '')[:28], '|', r['name'][:24],
          '|', ','.join(r['primery_pocht'][:2])[:40], '|', ','.join(r['primery_tel'][:2]))
