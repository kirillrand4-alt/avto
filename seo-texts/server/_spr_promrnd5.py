# -*- coding: utf-8 -*-
"""Сверка объёма promrnd: сколько id из каталожной страницы живые."""
import io
import json
import os
import re
import sys
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36 (+prokompressor.ru research)')
req = urllib.request.Request('https://promrnd.ru/company/', headers={'User-Agent': UA})
h = urllib.request.urlopen(req, timeout=40).read().decode('utf-8', 'replace')
кат = sorted({int(x) for x in re.findall(r'/company/(\d+)/', h)})
жив, мерт = set(), set()
p = r'C:\sender\_tmp\promrnd_cards.jsonl'
for ln in io.open(p, encoding='utf-8', errors='replace'):
    try:
        r = json.loads(ln)
    except Exception:
        continue
    (жив if r.get('st') == 200 else мерт).add(r['id'])
t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))
print(json.dumps({
    'id_на_каталожной_странице': len(кат), 'мин': min(кат), 'макс': max(кат),
    'из_них_живых': len(set(кат) & жив), 'из_них_404': len(set(кат) & мерт),
    'не_проверено': len(set(кат) - жив - мерт),
    'всего_проверено_id': len(жив) + len(мерт), 'живых_всего': len(жив),
    'счётчик_на_странице': re.findall(r'(?:Найдено|Всего|предприятий)[:\s]*([\d\s]{2,10})', t)[:4],
    'лог': open(r'C:\sender\_tmp\spr_promrnd.log', encoding='utf-8',
                errors='replace').read()[-160:] if os.path.exists(
        r'C:\sender\_tmp\spr_promrnd.log') else '',
}, ensure_ascii=False)[:2500])
