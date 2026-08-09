# -*- coding: utf-8 -*-
"""Сшивка трёх участков в одну строку: ЧЕЛОВЕК + РОЛЬ + ЛИЧНЫЙ НОМЕР + доказанная машина.

Это и есть цель владельца целиком, и ни у кого из нас троих её нет по отдельности:

    2-я сессия  имя ЛПР с ролью, проверенной рядом с ним      42 имени на 22 предприятиях
    3-я (я)     личный номер с доказанной принадлежностью     17 номеров на 13 предприятиях
    1-я + 2-я   доказанная машина со ссылкой                  2 300 ИНН

Сшиваю по ИНН и по человеку. Ключ человека — фамилия плюс инициалы, потому что у неё
«Володин Павел Николаевич», а у меня может быть «Володин П.Н.»: сравнение полных строк
потеряет верные совпадения.

ЧЕТЫРЕ ИСХОДА, и каждый называется, а не сваливается в «нашлось»:

    ПОЛНЫЙ    человек с ролью И его личный номер И машина у предприятия — цель достигнута
    ЧЕЛОВЕК БЕЗ НОМЕРА  роль есть, номера нет: это очередь на обратный поиск
    НОМЕР БЕЗ ЧЕЛОВЕКА  номер личный, но чьё имя — не подтверждено ролью
    РАЗНЫЕ ЛЮДИ         на предприятии есть и то и другое, но это РАЗНЫЕ люди. Такую строку
                        нельзя выдавать за полную: соединять имя одного с номером другого —
                        ровно та ошибка, которой мы весь день учимся не делать.

Только чтение. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import urllib.request

MOI = [r'C:\sender\_ops\PARK-KONTAKTY-3S-CHESTNO.jsonl',
       r'C:\sender\_ops\PARK-OBRATNYY-PROVERENO-3S.jsonl',
       r'C:\sender\_ops\PARK-OBRATNYY-1S-PROVERENO-3S.jsonl',
       r'C:\sender\_ops\PARK-OBRATNYY-2S-PROVERENO-3S.jsonl',
       # Два потока обратного хода лежали в песочнице непроверенными: 3 771 и 911 человек,
       # пройденных ранее и НИ РАЗУ не пропущенных через заслоны. Дали 54 и 21 личный номер.
       r'C:\sender\_ops\PARK-OBRATNYY-STARYY-PROVERENO-3S.jsonl',
       r'C:\sender\_ops\PARK-OBRATNYY-STARYY2-PROVERENO-3S.jsonl']
SOSED = 'PARK-KONTAKTY-2S.csv'
PARK = [r'C:\sender\_ops\park_ingest_3.jsonl', r'C:\sender\_ops\park_ingest_3b.jsonl',
        r'C:\sender\_ops\park_ingest_3c.jsonl']
VYHOD = r'C:\sender\_ops\PARK-SVODKA-CHELOVEK-ROL-NOMER-3S.jsonl'


def klyuch_cheloveka(fio):
    ch = re.sub(r'[^А-ЯЁа-яё\s\.\-]', ' ', fio or '').split()
    if not ch:
        return ''
    fam = ch[0].upper()
    ini = ''.join(x[0].upper() for x in ch[1:3] if x)
    return '%s %s' % (fam, ini)


op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# машина у предприятия
mashina = {}
for p in PARK:
    if not os.path.exists(p):
        continue
    for s in io.open(p, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        if o.get('inn'):
            mashina.setdefault(o['inn'], o.get('vid') or 'машина')

# мои личные номера
moi_nomera = collections.defaultdict(list)
for p in MOI:
    if not os.path.exists(p):
        continue
    for s in io.open(p, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        if o.get('vid_nomera') == 'ЛИЧНЫЙ МОБИЛЬНЫЙ' and o.get('nomer'):
            moi_nomera[o['inn']].append(o)

# люди с ролью от соседа
try:
    syr = op.open(urllib.request.Request(
        '%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'), SOSED),
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}),
        timeout=180).read().decode('utf-8-sig', 'replace')
except Exception as e:  # noqa: BLE001
    syr = ''
    print('файл соседа не скачался: %s' % str(e)[:80])
lyudi = collections.defaultdict(list)
for s in syr.splitlines()[1:]:
    p = s.split(';')
    # У 377 строк из 3 062 полей больше девяти: точка с запятой стоит внутри значения.
    # Слепой индекс p[5] на таких строках берёт не человека, а кусок цитаты. Лишнее
    # склеиваю обратно в ПОСЛЕДНЮЮ колонку (цитата) — свободный текст, где разделитель и
    # встречается. Это не догадка: колонок ровно девять по шапке файла.
    if len(p) > 9:
        p = p[:8] + [';'.join(p[8:])]
    if len(p) < 9 or not p[0].strip().isdigit():
        continue
    chel, dolzh = p[5].strip(), p[6].strip()
    if not chel or len(chel) < 5:
        continue
    lyudi[p[0].strip()].append({'chelovek': chel, 'dolzhnost': dolzh,
                                'ssylka': p[7].strip(), 'citata': p[8].strip()[:200]})

potok, ishody = [], collections.Counter()

# ПОЛНАЯ СТРОКА ИЗ ОДНОГО ИСТОЧНИКА. Сшивать с чужим файлом нужно не всегда: в потоках
# обратного хода имя, должность и номер стоят в ОДНОЙ строке, добытые вместе и с одной
# ссылкой. Такие беру как полные сразу, не пытаясь найти второе подтверждение на стороне.
for inn, spisok in moi_nomera.items():
    for n in spisok:
        if n.get('imya') and n.get('dolzhnost'):
            ishody['ПОЛНЫЙ: имя, должность и номер в одной строке обратного хода'] += 1
            potok.append({'inn': inn, 'ishod': 'ПОЛНЫЙ',
                          'chelovek': n['imya'], 'dolzhnost': n['dolzhnost'],
                          'nomer': n['nomer'], 'mashina': mashina.get(inn, ''),
                          'istochniki': n.get('istochniki', ''), 'istochnikov': 1,
                          'kto': '3-я сессия, обратный ход'})


for inn in set(list(moi_nomera) + list(lyudi)):
    nom, lyu = moi_nomera.get(inn, []), lyudi.get(inn, [])
    if nom and lyu:
        sovpali = []
        for n in nom:
            k = klyuch_cheloveka(n.get('imya') or '')
            for l in lyu:
                if k and k == klyuch_cheloveka(l['chelovek']):
                    sovpali.append((n, l))
        if sovpali:
            for n, l in sovpali:
                ishody['ПОЛНЫЙ: человек, роль и его личный номер'] += 1
                potok.append({'inn': inn, 'ishod': 'ПОЛНЫЙ',
                              'chelovek': l['chelovek'], 'dolzhnost': l['dolzhnost'],
                              'nomer': n['nomer'], 'mashina': mashina.get(inn, ''),
                              'istochniki': ' | '.join(x for x in (n.get('istochniki'),
                                                                   l['ssylka']) if x),
                              'istochnikov': 2, 'kto': '3-я сессия, сводка'})
        else:
            ishody['РАЗНЫЕ ЛЮДИ: имя одного, номер другого — не сшиваю'] += 1
            potok.append({'inn': inn, 'ishod': 'РАЗНЫЕ ЛЮДИ',
                          'chelovek': lyu[0]['chelovek'], 'dolzhnost': lyu[0]['dolzhnost'],
                          'nomer': nom[0]['nomer'], 'mashina': mashina.get(inn, ''),
                          'istochniki': ' | '.join(x for x in (nom[0].get('istochniki'),
                                                               lyu[0]['ssylka']) if x),
                          'istochnikov': 2, 'kto': '3-я сессия, сводка'})
    elif lyu:
        ishody['ЧЕЛОВЕК БЕЗ НОМЕРА: очередь на обратный поиск'] += len(lyu)
    elif nom:
        ishody['НОМЕР БЕЗ ПОДТВЕРЖДЁННОЙ РОЛИ'] += len(nom)

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for o in potok:
        f.write(json.dumps(o, ensure_ascii=False) + '\n')
try:
    rq = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                           os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT',
                                headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    vyl = op.open(rq, timeout=180).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    vyl = 'не выложено: %s' % str(e)[:80]

polnye = [o for o in potok if o['ishod'] == 'ПОЛНЫЙ']
print('\n\n########## ПОЛНЫЕ СТРОКИ, ПО ОДНОЙ')
for o in polnye[:10]:
    print('  %-12s %-28s %-24s %s  машина: %s' % (o['inn'], o['chelovek'][:28],
                                                  o['dolzhnost'][:24], o['nomer'],
                                                  o['mashina'][:18]))
print('\n########## ЧИСЛА')
print('  ИНН с машиной в парке          %5d' % len(mashina))
print('  ИНН, где есть мой личный номер %5d' % len(moi_nomera))
print('  ИНН, где есть человек с ролью  %5d' % len(lyudi))
for k, v in ishody.most_common():
    print('     %-52s %5d' % (k[:52], v))
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'полных': len(polnye),
                            'разные люди': sum(1 for o in potok if o['ishod'] == 'РАЗНЫЕ ЛЮДИ')},
                           ensure_ascii=False))
