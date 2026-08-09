# -*- coding: utf-8 -*-
"""Переложить словарь на дроп ПРАВИЛЬНО: API дропа — PUT на URL/<имя>, а не multipart.

Мой прошлый заход отправил multipart POST на `/up`, и дроп сохранил файл под именем «up»,
а второй файл затёр первый. Клиент `drop_client.sh` делает `curl -T "$2" "$U/$(basename)"`
— то есть PUT с именем в пути. Читать чужой рабочий клиент надо было ДО того, как писать
свой: это ровно тот класс, за который сегодня платили дважды.
"""
import io
import json
import os
import urllib.request

FAYLY = [r'C:\sender\_ops\PARK-SLOVAR-SERII-3S.csv',
         r'C:\sender\_ops\PARK-SLOVAR-SERII-PROVERIT-3S.csv']
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = os.environ.get('DROP_TOKEN', '')
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
itog = {}
for p in FAYLY:
    if not os.path.exists(p):
        itog[os.path.basename(p)] = 'файла нет'
        continue
    telo = io.open(p, 'rb').read()
    req = urllib.request.Request('%s/%s' % (drop, os.path.basename(p)), data=telo,
                                 method='PUT', headers={'X-Drop-Token': tok})
    try:
        itog[os.path.basename(p)] = op.open(req, timeout=180).read().decode('utf-8', 'replace')[:160]
    except Exception as e:  # noqa: BLE001
        itog[os.path.basename(p)] = 'СБОЙ: %s' % str(e)[:140]

# убрать мусорный «up», созданный прошлым заходом
try:
    req = urllib.request.Request('%s/up' % drop, method='DELETE', headers={'X-Drop-Token': tok})
    itog['удаление up'] = op.open(req, timeout=60).read().decode('utf-8', 'replace')[:120]
except Exception as e:  # noqa: BLE001
    itog['удаление up'] = str(e)[:120]

for k, v in itog.items():
    print('  %-40s %s' % (k, v))
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False)[:400])
