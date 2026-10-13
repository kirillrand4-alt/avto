# -*- coding: utf-8 -*-
"""fixK (локально, только чтение): статус юрлиц Беларуси по УНП – открытый реестр плательщиков МНС РБ
(grp.nalog.gov.by, api grp-public). Сервис ЕГР (egr.gov.by) с сервера и из песочницы не отвечает.

    python3 -I fixK_by_mns.py <список УНП.txt> <выход.json>

Поля ответа: vunp, vnaimp/vnaimk (название), vpadres (адрес), dreg (регистрация), vkods/ckodsost (состояние),
dlikv (дата ликвидации). Ответ не получен – «статус не проверен».
"""
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

VHOD, VYHOD = sys.argv[1], sys.argv[2]
URL = 'https://grp.nalog.gov.by/api/grp-public/data?unp=%s&charset=UTF-8&type=json'
unp = [x.strip() for x in open(VHOD, encoding='utf-8') if x.strip()]


def odno(u):
    for pop in range(3):
        try:
            req = urllib.request.Request(URL % u, headers={'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0'})
            t = urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace')
            o = json.loads(t) if t.strip() else {}
            return u, (o.get('row') or {'_pusto': t[:200]})
        except Exception as e:  # noqa: BLE001
            if pop == 2:
                return u, {'_oshibka': '%s: %s' % (type(e).__name__, str(e)[:120])}
            time.sleep(2 * (pop + 1))


rez = {}
with ThreadPoolExecutor(max_workers=3) as pool:
    for u, z in pool.map(odno, unp):
        rez[u] = z
json.dump(rez, open(VYHOD, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
sch = {}
for z in rez.values():
    k = z.get('vkods') or ('ошибка' if z.get('_oshibka') else 'нет ответа')
    sch[k] = sch.get(k, 0) + 1
print('УНП %d: %s -> %s' % (len(rez), sch, VYHOD))
