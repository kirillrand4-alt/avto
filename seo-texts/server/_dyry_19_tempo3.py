# -*- coding: utf-8 -*-
"""Замер темпа выемки контактов из кэша (для сметы починки дыры 3)."""
import gzip
import json
import os
import random
import re
import sys
import time

sys.path.insert(0, r'C:\sender\server')
os.environ['NO_BROWSER'] = '1'
KESH = r'C:\seostat\drop\pagecache'
import enrich_contacts as EC  # noqa: E402

d3 = json.load(open(r'C:\sender\_tmp\dyra3.json', encoding='utf-8'))
celi = d3['celi']
random.seed(99)
vyb = random.sample(celi, 40)
t0 = time.time()
p_all = t_all = 0
for inn in vyb:
    p = os.path.join(KESH, inn + '.json.gz')
    try:
        with gzip.open(p, 'rb') as f:
            j = json.loads(f.read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        continue
    po, te = set(), set()
    for pg in (j.get('pages') or []):
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
        po |= {e for e in pe if not EC._is_junk_email(e)}
        te |= ph
    p_all += len(po)
    t_all += len(te)
sek = time.time() - t0
print('40 компаний за %.1f сек = %.2f сек/компанию; почт %d, телефонов %d'
      % (sek, sek / 40, p_all, t_all))
print('полный прогон по %d компаниям: ~%.0f мин в один поток'
      % (len(celi), len(celi) * sek / 40 / 60))
p = r'C:\sender\_tmp\dyra1_pochinka.json'
print('dyra1_pochinka.json:', 'есть' if os.path.exists(p) else 'НЕТ')
