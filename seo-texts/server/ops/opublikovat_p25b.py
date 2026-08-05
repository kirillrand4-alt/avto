# -*- coding: utf-8 -*-
"""Публикую панель P25 (8014) под /p25 — маршрут лежит во вложенном subroute."""
import copy, io, json, os, sys, time, urllib.request
АДМИН = 'http://127.0.0.1:2019'
ПРИМЕНИТЬ = '--apply' in sys.argv

def взять(п):
    return json.loads(urllib.request.urlopen(АДМИН + п, timeout=20).read().decode())

def послать(п, тело, метод='PUT'):
    з = urllib.request.Request(АДМИН + п, data=json.dumps(тело).encode(),
                               headers={'Content-Type': 'application/json'}, method=метод)
    return urllib.request.urlopen(з, timeout=30).read().decode()

конф = взять('/config/')
вн = конф['apps']['http']['servers']['srv0']['routes'][2]['handle'][0]['routes']
образец, индекс = None, -1
for i, м in enumerate(вн):
    пути = []
    for с in (м.get('match') or []):
        пути += с.get('path') or []
    if any(п.startswith('/obzvon') for п in пути):
        образец, индекс = м, i
    if any(п.startswith('/p25') for п in пути):
        print('маршрут /p25 уже есть'); raise SystemExit
if образец is None:
    print('образец /obzvon не найден среди', len(вн), 'вложенных маршрутов')
    for i, м in enumerate(вн[:12]):
        print(' ', i, json.dumps(м, ensure_ascii=False)[:110])
    raise SystemExit

новый = copy.deepcopy(образец)
for с in (новый.get('match') or []):
    if 'path' in с:
        с['path'] = ['/p25', '/p25/*']
def подмена(о):
    if isinstance(о, dict):
        if о.get('handler') == 'reverse_proxy':
            for u in (о.get('upstreams') or []):
                if u.get('dial', '').endswith(':8012'):
                    u['dial'] = '127.0.0.1:8014'
        for v in о.values(): подмена(v)
    elif isinstance(о, list):
        for v in о: подмена(v)
подмена(новый)
print('образец — вложенный маршрут №', индекс)
print('новый:', json.dumps(новый, ensure_ascii=False)[:260])
if not ПРИМЕНИТЬ:
    print('СУХОЙ ПРОГОН'); raise SystemExit

бэкап = r'C:\seostat\drop\caddy-config-' + time.strftime('%Y%m%d-%H%M%S') + '.json'
with io.open(бэкап, 'w', encoding='utf-8') as ф:
    json.dump(конф, ф, ensure_ascii=False); ф.flush(); os.fsync(ф.fileno())
print('прежний конфиг сохранён:', os.path.basename(бэкап))
послать('/config/apps/http/servers/srv0/routes/2/handle/0/routes/0', новый)
time.sleep(2)
проверка = json.dumps(взять('/config/'), ensure_ascii=False)
print('в живом конфиге упоминаний /p25:', проверка.count('/p25'),
      '| 8014:', проверка.count('8014'))
