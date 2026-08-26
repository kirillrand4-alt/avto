# -*- coding: utf-8 -*-
"""Доказательства: берём находки (наша безсайтовая компания -> сайт из источника)
и ИДЁМ НА САЙТ. Ищем на нём ИНН/ОГРН компании — это жёсткая улика. Плюс имя.
Пишем в C:\\sender\\_tmp\\spr_dokaz.jsonl с fsync."""
import io
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
OUT = r'C:\sender\_tmp\spr_dokaz.jsonl'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36 (+prokompressor.ru research)')
БЮДЖЕТ = float(sys.argv[1]) if len(sys.argv) > 1 else 420.0
t0 = time.time()


def дом(s):
    s = (s or '').strip().lower()
    s = re.sub(r'^https?://', '', s).split('/')[0]
    return s[4:] if s.startswith('www.') else s


def грузи(p):
    r = []
    if os.path.exists(p):
        for ln in io.open(p, encoding='utf-8', errors='replace'):
            try:
                r.append(json.loads(ln))
            except Exception:
                pass
    return r


def get(url, tmo=20):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={
                'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9'}), timeout=tmo) as r:
            raw = r.read(900000)
            enc = 'utf-8'
            m = re.search(r'charset=([\w-]+)', r.headers.get('Content-Type', ''))
            if m:
                enc = m.group(1)
            return r.status, raw.decode(enc, 'replace')
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read(400000).decode('utf-8', 'replace')
        except Exception:
            return e.code, ''
    except Exception:
        return -1, ''


cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=30)
БС = "COALESCE(site,'')='' AND COALESCE(cand_site,'')=''"
канд = {}
# 1. checko: уже добытые site_checko у безсайтовых
for r in cx.execute(f"""SELECT r.inn, c.name, c.region, COALESCE(c.revenue_rub,0), r.site_checko
   FROM requisites r JOIN companies c ON c.inn=r.inn
   WHERE COALESCE(r.site_checko,'')!='' AND COALESCE(c.site,'')=''
     AND COALESCE(c.cand_site,'')=''"""):
    канд[r[0]] = {'inn': r[0], 'name': r[1], 'region': r[2], 'rev': r[3],
                  'домен': дом(r[4]), 'источник': 'checko (уже оплачено)'}
# 2. checko свежая выборка
for x in грузи(r'C:\sender\_tmp\checko_polosy.jsonl') + грузи(r'C:\sender\_tmp\checko_sample.jsonl'):
    if x.get('sites') and x['inn'] not in канд:
        канд[x['inn']] = {'inn': x['inn'], 'name': x['name'], 'region': x.get('region'),
                          'rev': x.get('rev') or 0, 'домен': дом(x['sites'][0]),
                          'источник': 'checko /contacts'}
# 3. o-zavodah и agrobase
пары = [(x['inn'], x.get('site'), 'o-zavodah.ru') for x in грузи(r'C:\sender\_tmp\ozav_cards.jsonl')
        if x.get('inn') and x.get('site')]
пары += [(x['inn'], (x.get('ext') or [''])[0], 'agrobase.ru')
         for x in грузи(r'C:\sender\_tmp\agro_cards.jsonl') if x.get('inn') and x.get('ext')]
инны = list({p[0] for p in пары})
есть = {}
for i in range(0, len(инны), 400):
    part = инны[i:i + 400]
    for r in cx.execute(f"SELECT inn, name, region, COALESCE(revenue_rub,0) FROM companies "
                        f"WHERE {БС} AND inn IN (%s)" % ','.join('?' * len(part)), part):
        есть[r[0]] = r
for inn, s, ист in пары:
    r = есть.get(inn)
    if r and inn not in канд:
        канд[inn] = {'inn': inn, 'name': r[1], 'region': r[2], 'rev': r[3],
                     'домен': дом(s), 'источник': ист}
cx.close()
сп = sorted(канд.values(), key=lambda x: -(x['rev'] or 0))
done = {json.loads(l)['inn'] for l in io.open(OUT, encoding='utf-8', errors='replace')
        } if os.path.exists(OUT) else set()
f = io.open(OUT, 'a', encoding='utf-8')
n = 0
for c in сп:
    if c['inn'] in done or time.time() - t0 > БЮДЖЕТ or not c['домен']:
        continue
    d = c['домен']
    улика, страницы = '', []
    for путь in ('', '/contacts/', '/kontakty/', '/about/'):
        if улика == 'ИНН':
            break
        time.sleep(0.5)
        st, h = get('https://' + d + путь)
        if st != 200 or not h:
            st, h = get('http://' + d + путь)
        if st != 200 or not h:
            continue
        страницы.append(путь or '/')
        txt = re.sub(r'[^\d]', '', re.sub(r'<[^>]+>', ' ', h))
        if c['inn'] in txt:
            улика = 'ИНН'
        elif not улика:
            t2 = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h)).lower()
            ядро = re.sub(r'^(ооо|оао|зао|ао|пао|нао|ип)\s*', '',
                          re.sub(r'["«»]', '', (c['name'] or '')).lower().strip())
            ядро = ядро.split()[0] if ядро else ''
            if len(ядро) >= 5 and ядро in t2:
                улика = 'имя'
    rec = dict(c, улика=улика or 'нет', страниц=len(страницы))
    n += 1
    f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    if n % 10 == 0:
        f.flush()
        os.fsync(f.fileno())
f.flush()
os.fsync(f.fileno())
f.close()
все = грузи(OUT)
св = {}
for r in все:
    s = св.setdefault(r['источник'], {'n': 0, 'ИНН': 0, 'имя': 0, 'нет': 0})
    s['n'] += 1
    s[r['улика']] = s.get(r['улика'], 0) + 1
print(json.dumps({'кандидатов_всего': len(сп), 'проверено': len(все),
                  'по_источникам': св}, ensure_ascii=False)[:3000])
