# -*- coding: utf-8 -*-
"""Чем добрать директора и финпоказатели: dadata (уже оплачена) и ГИР БО (бесплатно)."""
import json
import os
import ssl
import urllib.error
import urllib.request

ИНН = '2222849751'   # ООО «БЗВС» из видео
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))
o = {}

# 1. dadata: отдаёт ли руководителя.
ТОК = os.environ.get('DADATA_TOKEN', '')
try:
    req = urllib.request.Request(
        'https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party',
        data=json.dumps({'query': ИНН}).encode(),
        headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                 'Authorization': 'Token ' + ТОК})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
    s = (d.get('suggestions') or [{}])[0]
    дан = s.get('data') or {}
    o['dadata'] = {
        'имя': s.get('value'),
        'руководитель': дан.get('management'),
        'оквэд': дан.get('okved'),
        'капитал': дан.get('capital'),
        'финансы_в_ответе': дан.get('finance'),
        'сотрудников': дан.get('employee_count'),
        'есть_поля': sorted([k for k in дан.keys()])[:24],
    }
except Exception as e:
    o['dadata'] = 'ОШИБКА: %r' % (e,)

# 2. ГИР БО (bo.nalog.ru) — первоисточник бухотчётности, открытый.
def гирбо(путь, тело=None):
    url = 'https://bo.nalog.ru' + путь
    h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
         'Accept': 'application/json', 'Referer': 'https://bo.nalog.ru/'}
    try:
        req = urllib.request.Request(url, data=тело, headers=h)
        with НП.open(req, timeout=45) as r:
            return r.getcode(), r.read(200000).decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, (e.read(300) or b'').decode('utf-8', 'replace')
    except Exception as e:
        return -1, repr(e)[:110]

код, тело = гирбо('/nbo/organizations/search?query=%s&page=0' % ИНН)
o['гирбо_поиск'] = {'код': код, 'ответ': тело[:600]}
try:
    орг = json.loads(тело)
    ид = (орг.get('content') or [{}])[0].get('id')
    o['гирбо_id'] = ид
    if ид:
        к2, т2 = гирбо('/nbo/organizations/%s/bfo/' % ид)
        o['гирбо_отчётность'] = {'код': к2, 'ответ': т2[:900]}
except Exception as e:
    o['гирбо_разбор'] = repr(e)[:90]

print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5000])
