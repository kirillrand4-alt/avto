# -*- coding: utf-8 -*-
"""Перепроверяю ЧУЖОЕ число своим прибором: «у 497 предприятий с машиной нет контактов вовсе».

2-я сессия записала в журнал:

    ИНН с фактом ЭПБ 658 | ИНН из ширины 962 | проверено 900
    почта есть у 345 | человек есть у 311 | телефон есть у 358 | сайт 270
    НИЧЕГО НЕТ у 497  (55 %)

У меня по СВОЕЙ выборке вышло почти обратное: из 439 ИНН парка контакт хоть какой-то есть у
375 (85 %). Два прибора над одними и теми же базами не могут давать 45 % и 85 % — значит
либо выборки разные, либо один из приборов смотрит не туда. Это стоит развести до того, как
кто-то из нас построит на своём числе план.

Беру ИХ список предприятий (файл с дропа) и меряю СВОИМ прибором: те же таблицы, тот же
десятизначный ключ номера, та же проверка почты. Печатаю три вещи:

    1. их число на их выборке моим прибором,
    2. моё число на моей выборке,
    3. пересечение выборок — потому что если оно мало, спорить не о чем, мы про разное.

Если разойдёмся — назову таблицы, которые вижу я и, судя по числу, не видит сосед.

Только чтение. Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import sqlite3
import urllib.request

FAJL_SOSEDA = 'PARK-FAKTY-2S-EPB-POLNYE.csv'
MOY_POTOK = r'C:\sender\_ops\park_ingest_3.jsonl'
BAZY = [r'C:\sender\enrich.db', r'C:\seostat\drop\drop-storage\atlas_copco.db',
        r'C:\seostat\data\centrifugal.db']
P_INN = re.compile(r'^(inn|company_inn|firma_inn|org_inn)$', re.I)
P_TEL = re.compile(r'phone|tel|mobil', re.I)
P_POCHTA = re.compile(r'email|mail', re.I)
P_IMYA = re.compile(r'^(name|fio|full_name|person|person_name|contact_name)$', re.I)
FIO = re.compile(r'^[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё\-]{2,}\s+'
                 r'[А-ЯЁ][а-яё\-]{2,}(?:ович|евич|ич|овна|евна|ична)$')


def desyat(t):
    c = re.sub(r'\D', '', str(t or ''))
    if len(c) == 11 and c[0] in '78':
        c = c[1:]
    return c if len(c) == 10 else ''


# --- их выборка
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
inn_soseda, oshibka = set(), ''
try:
    rq = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                           FAJL_SOSEDA),
                                headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    syr = op.open(rq, timeout=300).read().decode('utf-8-sig', 'replace')
    shapka = syr.split('\n', 1)[0].split(';')
    k = next((i for i, h in enumerate(shapka) if h.strip().lower() in ('inn', 'инн')), None)
    for s in syr.split('\n')[1:]:
        p = s.split(';')
        v = (p[k].strip() if k is not None and len(p) > k else '')
        if v.isdigit() and len(v) in (10, 12):
            inn_soseda.add(v)
except Exception as e:  # noqa: BLE001
    oshibka = str(e)[:90]

# --- моя выборка
inn_moi = set()
if os.path.exists(MOY_POTOK):
    for s in io.open(MOY_POTOK, encoding='utf-8'):
        try:
            inn_moi.add(json.loads(s)['inn'])
        except Exception:  # noqa: BLE001
            pass

interes = inn_soseda | inn_moi
est_tel, est_pochta, est_chelovek, gde_nashla = (collections.defaultdict(set),
                                                 collections.defaultdict(set),
                                                 collections.defaultdict(set),
                                                 collections.Counter())
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
        k_inn = [k for k in kol if P_INN.match(k)]
        k_tel = [k for k in kol if P_TEL.search(k)]
        k_pch = [k for k in kol if P_POCHTA.search(k)]
        k_im = [k for k in kol if P_IMYA.match(k)]
        if not k_inn or not (k_tel or k_pch or k_im):
            continue
        metka = '%s/%s' % (os.path.basename(baza), t)
        try:
            kur = cx.execute('select %s from "%s"' % (','.join('"%s"' % k for k in kol), t))
        except Exception:  # noqa: BLE001
            continue
        for r in kur:
            d = dict(zip(kol, r))
            inn = str(d.get(k_inn[0]) or '').strip()
            if inn not in interes:
                continue
            for kt in k_tel:
                if desyat(d.get(kt)):
                    est_tel[inn].add(metka)
                    gde_nashla['телефон ' + metka] += 1
            for kp in k_pch:
                v = str(d.get(kp) or '').strip().lower()
                if '@' in v and ' ' not in v:
                    est_pochta[inn].add(metka)
                    gde_nashla['почта ' + metka] += 1
            for ki in k_im:
                v = re.sub(r'\s+', ' ', str(d.get(ki) or '')).strip()
                if FIO.match(v):
                    est_chelovek[inn].add(metka)
                    gde_nashla['человек ' + metka] += 1
    cx.close()


def svod(nabor, imya):
    t = sum(1 for i in nabor if est_tel.get(i))
    p = sum(1 for i in nabor if est_pochta.get(i))
    c = sum(1 for i in nabor if est_chelovek.get(i))
    nich = sum(1 for i in nabor
               if not est_tel.get(i) and not est_pochta.get(i) and not est_chelovek.get(i))
    print('  %-26s ИНН %5d | телефон %5d | почта %5d | человек %5d | НИЧЕГО %5d (%.0f %%)'
          % (imya, len(nabor), t, p, c, nich, 100.0 * nich / max(1, len(nabor))))
    return {'инн': len(nabor), 'телефон': t, 'почта': p, 'человек': c, 'ничего': nich}


print('\n\n########## ОДНИМ ПРИБОРОМ ПО ДВУМ ВЫБОРКАМ')
if oshibka:
    print('  файл соседа не скачался: %s' % oshibka)
a = svod(inn_soseda, 'выборка 2-й сессии') if inn_soseda else {}
b = svod(inn_moi, 'моя выборка (парк)') if inn_moi else {}
peres = inn_soseda & inn_moi
print('  пересечение выборок        %5d  (%.0f %% моей, %.0f %% их)'
      % (len(peres), 100.0 * len(peres) / max(1, len(inn_moi)),
         100.0 * len(peres) / max(1, len(inn_soseda))))
print('\n########## ГДЕ ИМЕННО НАХОДИТСЯ КОНТАКТ (топ таблиц)')
for k, v in gde_nashla.most_common(12):
    print('     %-52s %7d' % (k[:52], v))
print('\n########## ЧИСЛА')
print('  сосед записал: НИЧЕГО НЕТ у 497 из 900 (55 %)')
if a:
    print('  мой прибор на ИХ выборке: НИЧЕГО НЕТ у %d из %d (%.0f %%)'
          % (a['ничего'], a['инн'], 100.0 * a['ничего'] / max(1, a['инн'])))
    print('  СОШЛОСЬ' if abs(a['ничего'] - 497) <= 60 else '  НЕ СОШЛОСЬ — расходимся, разбирать')
print('ИТОГ ' + json.dumps({'их выборка': a, 'моя выборка': b, 'пересечение': len(peres)},
                           ensure_ascii=False))
