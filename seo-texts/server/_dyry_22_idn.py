# -*- coding: utf-8 -*-
"""Теряет ли база кириллические (.рф) домены: сверка companies против кэша."""
import gzip
import json
import os
import random
import re
import sqlite3

RO = 'file:C:/sender/enrich.db?mode=ro'
KESH = r'C:\seostat\drop\pagecache'
NEASCII = re.compile(r'[^\x00-\x7f]')

c = sqlite3.connect(RO, uri=True, timeout=60)
vsego = c.execute('select count(*) from companies').fetchone()[0]
s_sajtom = c.execute("select count(*) from companies where coalesce(site,'')<>'' "
                     "or coalesce(cand_site,'')<>''").fetchone()[0]
idn_site = c.execute(
    "select count(*) from companies where coalesce(site,'') glob '*[^ -~]*'").fetchone()[0]
idn_cand = c.execute(
    "select count(*) from companies where coalesce(cand_site,'') glob '*[^ -~]*'").fetchone()[0]
puny = c.execute("select count(*) from companies where coalesce(site,'') like '%xn--%' "
                 "or coalesce(cand_site,'') like '%xn--%'").fetchone()[0]
print('companies %d, с сайтом %d' % (vsego, s_sajtom))
print('site с не-ASCII: %d | cand_site с не-ASCII: %d | punycode xn--: %d'
      % (idn_site, idn_cand, puny))
komp = {}
for r in c.execute("select inn, coalesce(site,''), coalesce(cand_site,'') from companies"):
    komp[str(r[0])] = (r[1], r[2])
c.close()

# в кэше: сколько файлов записали .рф-сайт и что у них в companies
fajly = [n for n in os.listdir(KESH) if n.endswith('.json.gz')]
random.seed(3)
proba = random.sample(fajly, 1500)
idn_kesh = 0
idn_i_pusto = 0
idn_i_est = 0
primery = []
for n in proba:
    inn = n.split('.')[0]
    try:
        with gzip.open(os.path.join(KESH, n), 'rb') as f:
            b = f.read(4000)
        m = re.search(r'"site"\s*:\s*"([^"]{0,120})"', b.decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        continue
    s = m.group(1) if m else ''
    if not NEASCII.search(re.sub(r'^https?://', '', s)):
        continue
    idn_kesh += 1
    ks, kc = komp.get(inn, ('', ''))
    if ks or kc:
        idn_i_est += 1
    else:
        idn_i_pusto += 1
        if len(primery) < 10:
            primery.append((inn, s[:44]))
print('ВЫБОРКА кэша %d файлов: с не-ASCII сайтом %d' % (len(proba), idn_kesh))
print('  из них в companies сайт ЕСТЬ: %d | ПУСТ: %d' % (idn_i_est, idn_i_pusto))
print('  примеры пустых:', json.dumps(primery, ensure_ascii=False)[:600])
print('оценка на весь кэш (%d файлов): не-ASCII сайтов ~%d, из них без сайта в базе ~%d'
      % (len(fajly), round(idn_kesh * len(fajly) / len(proba)),
         round(idn_i_pusto * len(fajly) / len(proba))))
