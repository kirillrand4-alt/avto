# -*- coding: utf-8 -*-
"""Проверка «домен на много компаний» на ПОЛНЫХ снимках (тест на болезнь
tenderguru/my-gkh) + точность против наших известных сайтов на полном o-zavodah."""
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
    s = s[4:] if s.startswith('www.') else s
    return s.split(':')[0]


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
O = {}
наборы = {
    'o-zavodah': [(x['inn'], дом(x.get('site'))) for x in грузи(r'C:\sender\_tmp\ozav_cards.jsonl')
                  if x.get('inn') and x.get('site')],
    'agrobase': [(x['inn'], дом((x.get('ext') or [''])[0]))
                 for x in грузи(r'C:\sender\_tmp\agro_cards.jsonl') if x.get('inn') and x.get('ext')],
    'promrnd': [(x['inn'], дом(x.get('site'))) for x in грузи(r'C:\sender\_tmp\promrnd_sites.jsonl')
                if x.get('inn') and x.get('site')],
}
for имя, пары in наборы.items():
    д = {}
    for inn, h in пары:
        if h:
            д.setdefault(h, set()).add(inn)
    много = sorted(((len(v), k) for k, v in д.items() if len(v) > 1), reverse=True)
    # точность против наших известных сайтов
    инны = [p[0] for p in пары]
    наш = {}
    for i in range(0, len(инны), 400):
        part = инны[i:i + 400]
        for r in cx.execute("SELECT inn, COALESCE(site,''), substr(name,1,26) FROM companies "
                            "WHERE inn IN (%s)" % ','.join('?' * len(part)), part):
            наш[r[0]] = r
    сов = рас = 0
    прим = []
    for inn, h in пары:
        r = наш.get(inn)
        if not r or not r[1]:
            continue
        нд = дом(r[1])
        if нд == h or нд.endswith('.' + h) or h.endswith('.' + нд):
            сов += 1
        else:
            рас += 1
            if len(прим) < 5:
                прим.append([r[2], 'наш:' + нд, 'ист:' + h])
    O[имя] = {'пар_сайт': len(пары), 'уникальных_доменов': len(д),
              'доменов_на_1_компанию': sum(1 for v in д.values() if len(v) == 1),
              'доменов_на_2+': len(много), 'максимум_компаний_на_домен': много[0] if много else None,
              'топ_коллизий': много[:6],
              'сверка_с_нашими': {'пересечений': сов + рас, 'совпало': сов, 'разошлось': рас,
                                  'точность_%': round(100.0 * сов / max(1, сов + рас), 1),
                                  'примеры': прим}}
cx.close()
with open(r'C:\sender\_tmp\spr_kolliz.json', 'w', encoding='utf-8') as f:
    json.dump(O, f, ensure_ascii=False, indent=1)
    f.flush()
    os.fsync(f.fileno())
print(json.dumps(O, ensure_ascii=False)[:4500])
