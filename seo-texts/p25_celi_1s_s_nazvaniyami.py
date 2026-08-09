# -*- coding: utf-8 -*-
"""Беру «главную дыру» 1-й сессии — 909 технических людей без номера — и готовлю их к обходу.

1-я сессия выложила `PARK-1S-CEL-OBRATNOGO-POISKA.csv` и записала: «список выложен, ждёт
того, кто возьмёт обратный поиск». Беру: машинерия обратного хода у меня, и все заслоны к
ней уже оплачены сегодня (номер обязан стоять в цитате телефонным образцом; хозяин номера —
ближайшее полное ФИО, мерено от конца предшествующего имени; сборники утёкших данных
исключаются; номер у нескольких ИНН не личный).

Одно дополнение перед обходом. Их файл даёт ИНН, ФИО и должность, но НЕ даёт названия
предприятия, а запрос вида «"Фамилия Имя Отчество" "<компания>"» без второй кавычки
вырождается в поиск однофамильцев по всей стране. Прошлый замер это уже показал: полное имя
компании дало 10 доказуемых из 12 против 3 у аббревиатуры. Поэтому подставляю названия из
боевой базы и печатаю, скольким не нашлось названия — они пойдут отдельной, слабой очередью.

Только чтение. Числа в КОНЦЕ.
"""
import collections
import io
import os
import re
import sqlite3
import urllib.request

FAJL = 'PARK-1S-CEL-OBRATNOGO-POISKA.csv'
VYHOD = r'C:\sender\_ops\PARK-CELI-1S-S-NAZVANIYAMI.csv'
BAZY = [r'C:\sender\enrich.db', r'C:\seostat\data\centrifugal.db',
        r'C:\seostat\drop\drop-storage\atlas_copco.db']

op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
rq = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'), FAJL),
                            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
syr = op.open(rq, timeout=180).read().decode('utf-8-sig', 'replace')

stroki = []
for s in syr.splitlines()[1:]:
    p = s.split(';')
    if len(p) >= 3 and p[0].strip().isdigit():
        stroki.append({'inn': p[0].strip(), 'fio': p[1].strip(), 'dolzh': p[2].strip(),
                       'rang': p[3].strip() if len(p) > 3 else '',
                       'ssylka': p[4].strip() if len(p) > 4 else ''})

imena = {}
for baza in BAZY:
    if not os.path.exists(baza):
        continue
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % baza.replace('\\', '/'), uri=True)
        tabl = [r[0] for r in cx.execute("select name from sqlite_master where type='table'")]
    except Exception:  # noqa: BLE001
        continue
    for t in tabl:
        try:
            kol = [r[1] for r in cx.execute('pragma table_info("%s")' % t)]
        except Exception:  # noqa: BLE001
            continue
        if 'inn' not in kol:
            continue
        pn = next((k for k in ('name', 'naimenovanie', 'company', 'predpriyatie') if k in kol), None)
        if not pn:
            continue
        try:
            for inn, nm in cx.execute('select inn, "%s" from "%s" where "%s" is not null'
                                      % (pn, t, pn)):
                i = str(inn or '').strip()
                v = re.sub(r'\s+', ' ', str(nm)).strip()
                if i and len(v) > 4 and i not in imena:
                    imena[i] = v
        except Exception:  # noqa: BLE001
            continue
    cx.close()

s_imenem = [o for o in stroki if imena.get(o['inn'])]
bez = [o for o in stroki if not imena.get(o['inn'])]
with io.open(VYHOD, 'w', encoding='utf-8-sig') as f:
    f.write('inn;predpriyatie;fio;dolzhnost;rang;ssylka_1s\n')
    for o in s_imenem + bez:
        f.write(';'.join([o['inn'], imena.get(o['inn'], '').replace(';', ','),
                          o['fio'].replace(';', ','), o['dolzh'].replace(';', ','),
                          o['rang'], o['ssylka'].replace(';', ',')]) + '\n')
try:
    r2 = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                           os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT',
                                headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    vyl = op.open(r2, timeout=180).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    vyl = 'не выложено: %s' % str(e)[:80]

polnoe = sum(1 for o in stroki if len(o['fio'].split()) >= 3)
print('\n\n########## ПРИМЕРЫ')
for o in s_imenem[:6]:
    print('  %-12s %-30s %-24s %s' % (o['inn'], o['fio'][:30], o['dolzh'][:24],
                                      imena[o['inn']][:40]))
print('\n########## ЧИСЛА')
print('  людей в файле 1-й сессии     %5d' % len(stroki))
print('  из них с полным ФИО          %5d  (остальным обратный ход бесполезен)' % polnoe)
print('  название предприятия найдено %5d' % len(s_imenem))
print('  названия НЕТ                 %5d  (слабая очередь)' % len(bez))
print('  разных ИНН                   %5d' % len({o['inn'] for o in stroki}))
print('  --- должности')
for k, v in collections.Counter(o['dolzh'] for o in stroki).most_common(8):
    print('     %-34s %5d' % (k[:34], v))
print('  файл: %s' % VYHOD)
print('  выложено: %s' % vyl)
print('ИТОГ {"людей": %d, "с названием": %d, "с полным ФИО": %d}'
      % (len(stroki), len(s_imenem), polnoe))
