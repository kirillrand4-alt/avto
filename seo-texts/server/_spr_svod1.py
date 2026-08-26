# -*- coding: utf-8 -*-
"""Свод: (1) сколько уже добытых checko-сайтов лежит незаписанными;
(2) сопоставление снятых карточек o-zavodah с нашей базой по ИНН."""
import io
import json
import os
import re
import sqlite3
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
O = {}
cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=30)
БС = "COALESCE(c.site,'')='' AND COALESCE(c.cand_site,'')=''"
O['уже_добытое'] = dict(zip(
    ['req_site_checko_всего', 'из_них_компания_без_сайта', 'comp_site_checko_всего',
     'comp_site_checko_без_сайта'],
    cx.execute(f"""SELECT
      (SELECT COUNT(*) FROM requisites WHERE COALESCE(site_checko,'')!=''),
      (SELECT COUNT(*) FROM requisites r JOIN companies c ON c.inn=r.inn
        WHERE COALESCE(r.site_checko,'')!='' AND {БС}),
      (SELECT COUNT(*) FROM companies WHERE COALESCE(site_checko,'')!=''),
      (SELECT COUNT(*) FROM companies c WHERE COALESCE(c.site_checko,'')!='' AND {БС})
      """).fetchone()))
O['примеры_незаписанных'] = cx.execute(f"""
  SELECT r.inn, substr(c.name,1,34), r.site_checko, COALESCE(c.revenue_rub,0)
  FROM requisites r JOIN companies c ON c.inn=r.inn
  WHERE COALESCE(r.site_checko,'')!='' AND {БС}
  ORDER BY COALESCE(c.revenue_rub,0) DESC LIMIT 8""").fetchall()

# --- o-zavodah сопоставление
p = r'C:\sender\_tmp\ozav_cards.jsonl'
z = []
if os.path.exists(p):
    for ln in io.open(p, encoding='utf-8', errors='replace'):
        try:
            z.append(json.loads(ln))
        except Exception:
            pass
O['ozav_снято'] = len(z)
инны = [x['inn'] for x in z if x.get('inn')]
O['ozav_с_инн'] = len(инны)
O['ozav_с_сайтом'] = sum(1 for x in z if x.get('site'))
# сколько наших
наши = {}
for i in range(0, len(инны), 400):
    part = инны[i:i + 400]
    q = ("SELECT inn, substr(name,1,40), region, COALESCE(revenue_rub,0), "
         "COALESCE(site,''), COALESCE(cand_site,'') FROM companies WHERE inn IN (%s)"
         % ','.join('?' * len(part)))
    for r in cx.execute(q, part):
        наши[r[0]] = r
O['ozav_наших'] = len(наши)
O['ozav_наших_без_сайта'] = sum(1 for r in наши.values() if not r[4] and not r[5])
дом = {}
for x in z:
    s = (x.get('site') or '').strip()
    if not s:
        continue
    h = re.sub(r'^https?://', '', s).split('/')[0].lower()
    if h.startswith('www.'):
        h = h[4:]
    дом.setdefault(h, []).append(x.get('inn'))
многие = sorted(((len(v), k) for k, v in дом.items() if len(v) > 1), reverse=True)[:12]
O['ozav_домен_на_много_компаний'] = многие
O['ozav_доменов_уникальных'] = len(дом)
O['ozav_доменов_на_1_компанию'] = sum(1 for v in дом.values() if len(v) == 1)
# наши без сайта + карточка с сайтом
нах = []
for x in z:
    r = наши.get(x.get('inn'))
    if r and not r[4] and not r[5] and x.get('site'):
        нах.append([r[0], r[1], r[2], int(r[3] or 0), x['site'][:48]])
нах.sort(key=lambda a: -a[3])
O['ozav_находок_для_безсайтовых'] = len(нах)
O['ozav_топ_находок'] = нах[:10]
cx.close()
for f in ('spr_ozav.log', 'spr_agro.log'):
    try:
        O.setdefault('логи', {})[f] = open(r'C:\sender\_tmp\%s' % f,
                                           encoding='utf-8', errors='replace').read()[-120:]
    except Exception as e:
        O.setdefault('логи', {})[f] = str(e)[:50]
print(json.dumps(O, ensure_ascii=False)[:5700])
