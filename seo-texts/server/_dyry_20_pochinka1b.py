# -*- coding: utf-8 -*-
"""Цена починки дыры 1 (быстрый вариант): у скольких «без site» привязка доказуема.

Доказательство: ИНН или ОГРН компании стоит на её же странице в кэше.
Ищем подстрокой по сырому html (дёшево), с добором по цифрам только там,
где на странице вообще встречается слово ИНН. Есть бюджет времени.
Только чтение.
"""
import gzip
import json
import os
import re
import sqlite3
import time

RO = 'file:C:/sender/enrich.db?mode=ro'
KESH = r'C:\seostat\drop\pagecache'
BUDZHET = 700

d1 = json.load(open(r'C:\sender\_tmp\dyra1_itog.json', encoding='utf-8'))
zablok = set(d1['zablokirovany'])
stranic9 = set(d1['zablokirovany_9str'])

c = sqlite3.connect(RO, uri=True, timeout=60)
komp = {}
for r in c.execute("select inn, coalesce(name,''), coalesce(site,''), coalesce(cand_site,''), "
                   "coalesce(verified,''), coalesce(ogrn,'') from companies"):
    komp[str(r[0])] = tuple(r[1:])
tempo = [list(r) for r in c.execute(
    "select substr(ts,1,10) d, count(*) from site_facts where ts>='2026-08-20' "
    'group by d order by d')]
c.close()
print('паспортов в день:', json.dumps(tempo, ensure_ascii=False))

bez_sajta = sorted(i for i in zablok if i in komp and komp[i][3] != 'mismatch'
                   and not (komp[i][1] or komp[i][2]))
print('заблокированы пустыми site/cand_site:', len(bez_sajta))

t0 = time.time()
dok, ned = [], []
bez_fajla = obrabotano = 0
for inn in bez_sajta:
    if time.time() - t0 > BUDZHET:
        break
    p = os.path.join(KESH, inn + '.json.gz')
    try:
        with gzip.open(p, 'rb') as f:
            j = json.loads(f.read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        bez_fajla += 1
        continue
    obrabotano += 1
    ogrn = re.sub(r'\D', '', komp[inn][4])
    nash = False
    for pg in (j.get('pages') or [])[:12]:
        h = pg.get('html') or ''
        if not h:
            continue
        if inn in h or (ogrn and ogrn in h):
            nash = True
            break
        if 'ИНН' in h or 'инн' in h.lower():
            cif = re.sub(r'\D', '', h[:150000])
            if inn in cif or (ogrn and ogrn in cif):
                nash = True
                break
    rec = {'inn': inn, 'name': komp[inn][0][:44], 'kesh_site': (j.get('site') or '')[:48],
           'stranic': len(j.get('pages') or []), 'devyat': inn in stranic9}
    (dok if nash else ned).append(rec)
    if obrabotano % 400 == 0:
        print('  ...%d/%d %ds доказано %d' % (obrabotano, len(bez_sajta),
                                              time.time() - t0, len(dok)), flush=True)

vsego = len(dok) + len(ned)
print('ОБРАБОТАНО %d из %d за %ds' % (vsego, len(bez_sajta), time.time() - t0))
print('привязка ДОКАЗАНА (ИНН/ОГРН на своей странице): %d (%.0f%%)'
      % (len(dok), 100.0 * len(dok) / max(1, vsego)))
print('  из них >=9 страниц:', sum(1 for r in dok if r['devyat']))
print('НЕ доказана: %d; кэш не прочитался: %d' % (len(ned), bez_fajla))
if vsego < len(bez_sajta):
    print('ЭКСТРАПОЛЯЦИЯ на все %d: доказано ~%d' % (
        len(bez_sajta), round(len(dok) * len(bez_sajta) / max(1, vsego))))
dm = {}
for r in dok:
    x = re.sub(r'^https?://(www\.)?', '', r['kesh_site']).split('/')[0]
    dm[x] = dm.get(x, 0) + 1
print('топ доменов доказанных:', json.dumps(
    dict(sorted(dm.items(), key=lambda x: -x[1])[:10]), ensure_ascii=False)[:500])

with open(r'C:\sender\_tmp\dyra1_pochinka.json', 'w', encoding='utf-8') as f:
    json.dump({'dokazan': dok, 'ne_dokazan': ned, 'obrabotano': vsego,
               'vsego_bez_sajta': len(bez_sajta), 'tempo': tempo}, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
print('30 ПРИМЕРОВ ДОКАЗАННЫХ:')
for r in sorted(dok, key=lambda x: -x['stranic'])[:30]:
    print(' ', r['inn'], '|стр', r['stranic'], '|', r['kesh_site'][:38], '|', r['name'][:30])
