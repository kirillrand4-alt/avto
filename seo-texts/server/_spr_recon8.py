# -*- coding: utf-8 -*-
"""Разведка 8: почему на части карточек checko нет блока «Веб-сайты»; /contacts."""
import io
import json
import os
import re
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')


def get(url, tmo=40):
    hd = {'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
          'Accept': 'text/html,application/xhtml+xml,*/*'}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hd), timeout=tmo) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode('utf-8', 'replace')
        except Exception:
            return e.code, ''
    except Exception as e:
        return -1, str(e)[:90]


def plain(h):
    h = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', h, flags=re.S | re.I)
    h = re.sub(r'<[^>]+>', ' ', h)
    for a, b in (('&nbsp;', ' '), ('&quot;', '"'), ('&mdash;', '—'), ('&amp;', '&'),
                 ('&#8209;', '-'), ('&ndash;', '-')):
        h = h.replace(a, b)
    return re.sub(r'\s+', ' ', h)


R = {}
цели = [('7736216869', '1027700190572', 'ФОСАГРО'),
        ('1660004878', '1027739273331', 'КАЗАНЬКОМПРЕССОРМАШ'),
        ('0277106840', '1090280032699', 'БАШНЕФТЬ-ДОБЫЧА')]
# ОГРН точные возьмём из базы
import sqlite3
cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=30)
цели = [(i, cx.execute('SELECT ogrn FROM companies WHERE inn=?', (i,)).fetchone()[0], n)
        for i, _o, n in цели]
cx.close()
for inn, ogrn, nm in цели:
    st, h = get('https://checko.ru/company/%s' % ogrn)
    t = plain(h)
    i = t.find('Контакты')
    R[nm] = {'ogrn': ogrn, 'st': st, 'len': len(h),
             'фрагмент_контакты': t[i:i + 560] if i >= 0 else 'НЕТ СЛОВА КОНТАКТЫ',
             'Веб': 'Веб' in t, 'веб_сырьё': ('Веб' in h)}
    time.sleep(1.6)
    st2, h2 = get('https://checko.ru/company/%s/contacts' % ogrn)
    t2 = plain(h2)
    j = t2.find('Веб')
    R[nm]['contacts_подстраница'] = {
        'st': st2, 'len': len(h2),
        'фраг': t2[max(0, j - 320):j + 260] if j >= 0 else t2[:340]}
    time.sleep(1.6)
try:
    prev = json.load(open(r'C:\sender\_tmp\spravochniki.json', encoding='utf-8'))
except Exception:
    prev = {}
prev['recon8'] = R
with open(r'C:\sender\_tmp\spravochniki.json', 'w', encoding='utf-8') as f:
    json.dump(prev, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps(R, ensure_ascii=False)[:5800])
