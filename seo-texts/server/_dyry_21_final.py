# -*- coding: utf-8 -*-
"""Финал: почему у доказанных пуст site (IDN?), темп выемки, дописать сводку."""
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

d = json.load(open(r'C:\sender\_tmp\dyra1_pochinka.json', encoding='utf-8'))
dok, ned = d['dokazan'], d['ne_dokazan']


def idn(u):
    x = re.sub(r'^https?://(www\.)?', '', u or '').split('/')[0]
    return bool(re.search(r'[^\x00-\x7f]', x)) or x.startswith('xn--')


print('ДОКАЗАННЫЕ %d: с не-ASCII доменом (.рф и т.п.) %d (%.0f%%)'
      % (len(dok), sum(1 for r in dok if idn(r['kesh_site'])),
         100.0 * sum(1 for r in dok if idn(r['kesh_site'])) / max(1, len(dok))))
print('НЕДОКАЗАННЫЕ %d: с не-ASCII доменом %d (%.0f%%)'
      % (len(ned), sum(1 for r in ned if idn(r['kesh_site'])),
         100.0 * sum(1 for r in ned if idn(r['kesh_site'])) / max(1, len(ned))))
pust_sajt = sum(1 for r in dok + ned if not (r['kesh_site'] or '').strip())
print('у скольких заблокированных в самом кэше сайт не записан:', pust_sajt)

# темп выемки контактов (дыра 3) с бюджетом
import enrich_contacts as EC  # noqa: E402

d3 = json.load(open(r'C:\sender\_tmp\dyra3.json', encoding='utf-8'))
celi = d3['celi']
random.seed(5)
vyb = random.sample(celi, 60)
t0, n = time.time(), 0
for inn in vyb:
    if time.time() - t0 > 240:
        break
    try:
        with gzip.open(os.path.join(KESH, inn + '.json.gz'), 'rb') as f:
            j = json.loads(f.read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        continue
    for pg in (j.get('pages') or []):
        h = pg.get('html') or ''
        if not h:
            continue
        EC._harvest_from_html(h)
        pt = re.sub(r'<[^>]+>', ' ',
                    re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I))
        EC.EMAIL_RE.findall(pt)
        list(EC.phones_in(pt))
    n += 1
sek = time.time() - t0
print('ВЫЕМКА: %d компаний за %.0f сек = %.1f сек/компанию; на %d компаний ~%.0f мин '
      'в один поток' % (n, sek, sek / max(1, n), len(celi), len(celi) * sek / max(1, n) / 60))

p = r'C:\sender\_tmp\diagnoz-dyry.json'
s = json.load(open(p, encoding='utf-8'))
s['dyra1_pasporta']['починка'] = {
    'заблокированы_пустым_site': d['vsego_bez_sajta'],
    'привязка_доказуема_ИНН_на_странице': len(dok),
    'из_них_9_и_более_страниц': sum(1 for r in dok if r['devyat']),
    'не_доказуема': len(ned),
    'доля_не_ASCII_доменов_у_доказанных': round(
        sum(1 for r in dok if idn(r['kesh_site'])) / max(1, len(dok)), 2),
    'список_доказанных': dok,
    'темп_разбора_паспортов_в_день': d['tempo']}
s['dyra3_kontakty']['починка'] = {
    'сек_на_компанию': round(sek / max(1, n), 1),
    'минут_на_весь_список': round(len(celi) * sek / max(1, n) / 60)}
with open(p, 'w', encoding='utf-8') as f:
    json.dump(s, f, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
print('ОБНОВЛЁН', p, os.path.getsize(p), 'байт')
