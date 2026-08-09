# -*- coding: utf-8 -*-
"""Названия для 353 безымянных целей я искала не там: они лежат в МОИХ ЖЕ потоках.

Прошлый заход построил очередь поиска ЛПР и честно назвал потерю: у 353 целей из 576 нет
названия предприятия, а без него запрос «"ФИО" "<компания>"» вырождается в поиск
однофамильцев по стране. Я искала названия в справочных таблицах баз — и там их нет.

Между тем в моих собственных потоках название стоит рядом с ИНН:

    PARK-EIS-ZAKAZCHIKI-3S.jsonl   поле `zakazchik`     — имя заказчика с карточки ЕИС
    park_ingest_3c.jsonl           поле `organizaciya`  — организатор закупки на ЭТП ГПБ

Это ровно тот случай, который я днём записала заслоном: прежде чем добывать новое,
посмотреть, что уже добыто. Второй раз за смену наступаю на то же место, поэтому пишу это
в шапке, а не в примечании.

И вторая починка того же ряда: поток 3c собран в песочнице и на сервер не влит, поэтому
серверный замер парка показывает 950 вместо 1 185, а 336 ИНН из ЭТП ГПБ в очередь не
попали вовсе. Качаю его с дропа сюда же.

Только чтение баз. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import sqlite3
import urllib.request

DROP = os.environ.get('DROP_URL', '').rstrip('/')
TOKEN = os.environ.get('DROP_TOKEN', '')
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MESTO = r'C:\sender\_ops'
S_DROPA = ['park_ingest_3c.jsonl']
POTOKI = [r'C:\sender\_ops\park_ingest_3.jsonl', r'C:\sender\_ops\park_ingest_3b.jsonl',
          r'C:\sender\_ops\park_ingest_3c.jsonl']
IMENA_IZ = [(r'C:\sender\_ops\PARK-EIS-ZAKAZCHIKI-3S.jsonl', 'zakazchik'),
            (r'C:\sender\_ops\park_ingest_3c.jsonl', 'organizaciya')]
UZHE = [r'C:\sender\_ops\CELI-PARK-3S.csv', r'C:\sender\_ops\CELI-PARK-OSTALNOY-3S.csv']
VYHOD = r'C:\sender\_ops\CELI-PARK-S-IMENAMI-3S.csv'
BAZY = [r'C:\sender\enrich.db', r'C:\seostat\data\centrifugal.db',
        r'C:\seostat\drop\drop-storage\atlas_copco.db']
KLASS = {'ГПА': 5, 'компрессор': 4, 'нагнетатель': 4, 'ВРУ': 4, 'генератор азота': 4,
         'генератор кислорода': 4, 'воздуходувка': 3, 'МКС / передвижная': 3, 'осушитель': 2}
skachano = {}
for f in S_DROPA:
    put = os.path.join(MESTO, f)
    try:
        d = op.open(urllib.request.Request('%s/%s' % (DROP, f),
                                           headers={'X-Drop-Token': TOKEN}),
                    timeout=300).read()
        io.open(put, 'wb').write(d)
        skachano[f] = len(d)
    except Exception as e:  # noqa: BLE001
        skachano[f] = 'не скачан: %s' % str(e)[:60]

park = {}
for p in POTOKI:
    if not os.path.exists(p):
        continue
    for s in io.open(p, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        i = o.get('inn')
        if not i:
            continue
        v = o.get('vid') or 'машина'
        if i not in park or KLASS.get(v, 0) > KLASS.get(park[i], 0):
            park[i] = v

# 1) названия из баз
imena = {}
for b in BAZY:
    if not os.path.exists(b):
        continue
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % b.replace('\\', '/'), uri=True)
        tabl = [r[0] for r in cx.execute("select name from sqlite_master where type='table'")]
    except Exception:  # noqa: BLE001
        continue
    for t in tabl:
        try:
            kol = [r[1] for r in cx.execute('pragma table_info("%s")' % t)]
        except Exception:  # noqa: BLE001
            continue
        pn = next((k for k in ('name', 'naimenovanie', 'company', 'predpriyatie') if k in kol), None)
        if 'inn' not in kol or not pn:
            continue
        try:
            for i, n in cx.execute('select inn, "%s" from "%s" where "%s" is not null'
                                   % (pn, t, pn)):
                i = str(i or '').strip()
                v = re.sub(r'\s+', ' ', str(n)).strip()
                if i and len(v) > 4 and i not in imena:
                    imena[i] = v
        except Exception:  # noqa: BLE001
            continue
    cx.close()
iz_baz = len(imena)

# 2) названия из МОИХ ПОТОКОВ — то, чего я не сделала в прошлый раз
iz_potokov = 0
for put, pole in IMENA_IZ:
    if not os.path.exists(put):
        continue
    for s in io.open(put, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        i, v = o.get('inn'), re.sub(r'\s+', ' ', str(o.get(pole) or '')).strip()
        if i and len(v) > 4 and i not in imena:
            imena[i] = v
            iz_potokov += 1

uzhe = set()
for u in UZHE:
    if not os.path.exists(u):
        continue
    for s in io.open(u, encoding='utf-8-sig').read().splitlines()[1:]:
        p_ = s.split(';')
        if p_ and p_[0].strip().isdigit() and (len(p_) < 2 or p_[1].strip()):
            uzhe.add(p_[0].strip())      # спрошенными считаю только тех, у кого БЫЛО имя

celi = [{'inn': i, 'predpriyatie': imena.get(i, ''), 'mashina': v, 'klass': KLASS.get(v, 2)}
        for i, v in park.items() if i not in uzhe and imena.get(i)]
celi.sort(key=lambda o: -o['klass'])
with io.open(VYHOD, 'w', encoding='utf-8-sig') as f:
    f.write('inn;predpriyatie;mashina;klass\n')
    for o in celi:
        f.write(';'.join(str(o[k]).replace(';', ',') for k in
                         ('inn', 'predpriyatie', 'mashina', 'klass')) + '\n')
try:
    rq = urllib.request.Request('%s/%s' % (DROP, os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT',
                                headers={'X-Drop-Token': TOKEN})
    vyl = op.open(rq, timeout=180).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    vyl = 'не выложено: %s' % str(e)[:80]

bez = [i for i in park if not imena.get(i)]
print('\n\n########## ПЕРВЫЕ ДЕСЯТЬ НОВЫХ ЦЕЛЕЙ')
for o in celi[:10]:
    print('  %-12s %-48s %s' % (o['inn'], o['predpriyatie'][:48], o['mashina']))
print('\n########## ЧИСЛА')
for k, v in skachano.items():
    print('  скачано с дропа %-26s %s' % (k, v))
print('  ИНН в парке (теперь с 3c)   %5d' % len(park))
print('  названий из баз             %5d' % iz_baz)
print('  названий ДОБАВЛЕНО из моих потоков %5d' % iz_potokov)
print('  целей с именем на обход     %5d' % len(celi))
print('  осталось без имени вовсе    %5d' % len(bez))
print('  --- по машине')
for k, v in collections.Counter(o['mashina'] for o in celi).most_common():
    print('     %-26s %5d' % (k, v))
print('  файл: %s' % VYHOD)
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'парк': len(park), 'целей': len(celi),
                            'имён из потоков': iz_potokov, 'без имени': len(bez)},
                           ensure_ascii=False))
