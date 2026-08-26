# -*- coding: utf-8 -*-
"""ТОЧНОСТЬ источников: там, где мы САМИ знаем сайт компании (site непустой и
проверенный), сравниваем с тем, что даёт источник. Это прямая проверка «не
привяжем ли чужой сайт»."""
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
    if s.startswith('www.'):
        s = s[4:]
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


def сверка(пары, метка):
    """пары: [(inn, домен_источника)]"""
    инны = [p[0] for p in пары]
    наш = {}
    for i in range(0, len(инны), 400):
        part = инны[i:i + 400]
        for r in cx.execute("SELECT inn, COALESCE(site,''), COALESCE(cand_site,''), "
                            "COALESCE(verified,''), substr(name,1,30) FROM companies "
                            "WHERE inn IN (%s)" % ','.join('?' * len(part)), part):
            наш[r[0]] = r
    сов, расх, нет = 0, 0, 0
    примеры = []
    for inn, d in пары:
        r = наш.get(inn)
        if not r or not r[1]:
            нет += 1
            continue
        нд = дом(r[1])
        if нд == d or нд.endswith('.' + d) or d.endswith('.' + нд):
            сов += 1
        else:
            расх += 1
            if len(примеры) < 8:
                примеры.append([r[4], 'наш:' + нд, 'ист:' + d, 'verified=' + (r[3] or '')[:12]])
    O[метка] = {'пар_с_нашим_сайтом': сов + расх, 'совпало': сов, 'разошлось': расх,
                'нет_нашего_сайта': нет,
                'точность_%': round(100.0 * сов / max(1, сов + расх), 1),
                'примеры_расхождений': примеры}


# 1. o-zavodah
z = грузи(r'C:\sender\_tmp\ozav_cards.jsonl')
сверка([(x['inn'], дом(x['site'])) for x in z if x.get('inn') and x.get('site')], 'o-zavodah')
# 2. agrobase производители
a = грузи(r'C:\sender\_tmp\agro_cards.jsonl')
сверка([(x['inn'], дом(x['ext'][0])) for x in a if x.get('inn') and x.get('ext')], 'agrobase')
# 3. checko (requisites.site_checko)
ч = [(r[0], дом(r[1])) for r in cx.execute(
    "SELECT inn, site_checko FROM requisites WHERE COALESCE(site_checko,'')!=''")]
сверка(ч, 'checko')
# 4. checko из свежей выборки полос
пол = грузи(r'C:\sender\_tmp\checko_polosy.jsonl') + грузи(r'C:\sender\_tmp\checko_sample.jsonl')
сверка([(x['inn'], дом(x['sites'][0])) for x in пол if x.get('sites')], 'checko_свежая_выборка')
cx.close()
print(json.dumps(O, ensure_ascii=False)[:5700])
