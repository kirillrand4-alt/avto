# -*- coding: utf-8 -*-
"""ИТОГ: цифры по каждому источнику + 30 примеров с доказательством."""
import io
import json
import os
import re
import sqlite3
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def дом(s):
    s = (s or '').strip().lower()
    s = re.sub(r'^https?://', '', s).split('/')[0]
    return (s[4:] if s.startswith('www.') else s).split(':')[0]


def грузи(p):
    r = []
    if os.path.exists(p):
        for ln in io.open(p, encoding='utf-8', errors='replace'):
            try:
                r.append(json.loads(ln))
            except Exception:
                pass
    return r


cx = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=30)
БС = "COALESCE(site,'')='' AND COALESCE(cand_site,'')=''"
O = {}
z = грузи(r'C:\sender\_tmp\ozav_cards.jsonl')
a = грузи(r'C:\sender\_tmp\agro_cards.jsonl')
apk = грузи(r'C:\sender\_tmp\agro_apk_sample.jsonl')


def карта(инны):
    m = {}
    инны = list({i for i in инны if i})
    for i in range(0, len(инны), 400):
        part = инны[i:i + 400]
        for r in cx.execute("SELECT inn, name, region, COALESCE(revenue_rub,0), "
                            "COALESCE(site,''), COALESCE(cand_site,'') FROM companies "
                            "WHERE inn IN (%s)" % ','.join('?' * len(part)), part):
            m[r[0]] = r
    return m


for имя, recs, поле in (('o-zavodah', z, 'site'), ('agrobase_произв', a, 'ext'),
                        ('agrobase_АПК_выборка', apk, 'ext')):
    инны = [x.get('inn') for x in recs if x.get('inn')]
    m = карта(инны)
    ссайтом = [x for x in recs if (x.get(поле) if поле == 'site' else (x.get('ext') or []))]
    наши_бс = [x for x in recs if m.get(x.get('inn'))
               and not m[x['inn']][4] and not m[x['inn']][5]]
    нах = [x for x in наши_бс if (x.get(поле) if поле == 'site' else (x.get('ext') or []))]
    крупные = [x for x in нах if (m[x['inn']][3] or 0) >= 1e7]
    O[имя] = {'карточек_снято': len(recs), 'с_ИНН': len(инны),
              'уникальных_ИНН': len(set(инны)), 'с_сайтом_на_карточке': len(ссайтом),
              'наших_по_ИНН': len(m), 'НЕ_наших': len(set(инны)) - len(m),
              'наших_без_сайта': len(наши_бс), 'находок_сайта': len(нах),
              'из_них_выручка_10млн+': len(крупные)}
# checko
O['checko_готовое'] = dict(zip(['site_checko_в_requisites', 'из_них_у_безсайтовых'],
                               cx.execute(f"""SELECT
   (SELECT COUNT(*) FROM requisites WHERE COALESCE(site_checko,'')!=''),
   (SELECT COUNT(*) FROM requisites r JOIN companies c ON c.inn=r.inn
     WHERE COALESCE(r.site_checko,'')!='' AND COALESCE(c.site,'')=''
       AND COALESCE(c.cand_site,'')='')""").fetchone()))
# карточки agrobase БЕЗ ИНН — можно ли их брать по имени
без_инн = [x for x in a if x.get('st') == 200 and not x.get('inn')]
O['agro_без_ИНН'] = {
    'штук': len(без_инн),
    'с_внешним_сайтом': sum(1 for x in без_инн if x.get('ext')),
    'с_русским_регионом': sum(1 for x in без_инн
                              if re.search(r'обл|край|Респ|Москв|Петербург|АО\)', x.get('region') or '')),
    'примеры': [[x.get('name', '')[:52], x.get('region', '')[:22], (x.get('ext') or [''])[0]]
                for x in без_инн[:8]]}
# 30 примеров
d = грузи(r'C:\sender\_tmp\spr_dokaz.jsonl')
d.sort(key=lambda x: (-(1 if x['улика'] == 'ИНН' else 0), -(x['rev'] or 0)))
O['доказано_всего'] = {'записей': len(d),
                       'улика_ИНН': sum(1 for x in d if x['улика'] == 'ИНН'),
                       'улика_имя': sum(1 for x in d if x['улика'] == 'имя'),
                       'нет_улики': sum(1 for x in d if x['улика'] == 'нет')}
O['примеры30'] = [[x['name'][:34], x['домен'], x['источник'][:18], x['улика'],
                   round((x['rev'] or 0) / 1e6, 1)] for x in d[:30]]
cx.close()
with open(r'C:\sender\_tmp\spr_itog.json', 'w', encoding='utf-8') as f:
    json.dump(O, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps(O, ensure_ascii=False)[:5800])
