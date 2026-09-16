# -*- coding: utf-8 -*-
"""ОБЪЕКТ «ПРОЕКТ» В `enrich.db`: приём ВХОДЯЩЕГО события, а не перегонка архива.

Хранение там же и так же, как новости: та же база `C:\\sender\\enrich.db`, новые
таблицы рядом с `signals`, колонки в стиле signals (inn, source, source_url, ts...).
Существующие таблицы не трогаются ни одной строкой.

ТОЧКА ВХОДА ПОТОКА — одна функция:

    prinyat_sobytie(con, row, slov) -> (proekt_id, 'новый'|'дополнен'|'уже было', причина)

`row` — ровно та запись, которую коллектор кладёт в `signals`
(inn, source, event_type, what, sum, source_url, hotness, ts). Вызов ставится сразу
после вставки сигнала: событие пришло -> нашёлся проект -> добавили ДОКАЗАТЕЛЬСТВО;
не нашёлся -> завели проект. Доказательства НАКАПЛИВАЮТСЯ: у каждого свой источник,
ссылка, цитата, дата, и повторная подача того же события ничего не перезаписывает
(ключ доказательства — хэш источник+ссылка+цитата, вставка INSERT OR IGNORE).

ТАБЛИЦЫ (все новые, префикс как у signals — без префикса, имена говорящие):
    proekty          карточка проекта: ключ, стадия, дата стадии, регион, место,
                     заказчик (ИНН + название), сумма, отрасль, счётчики источников
    proekt_uliki     доказательства: источник, ссылка, цитата, дата — по строке на улику
    proekt_slovar    замороженный корпусный словарь основ (df, заглавные/строчные, форма)
    proekt_gashenie  якоря без различающей силы внутри ИНН (собственное имя компании)

Словарь ЗАМОРОЖЕН намеренно: признак «имя собственное» считается по доле написаний с
заглавной буквы в корпусе, и если бы он пересчитывался на каждом событии, вчерашняя
склейка переставала бы воспроизводиться. Пересчёт — отдельной командой `--slovar`.

Команды:
    --shema            создать таблицы (CREATE TABLE IF NOT EXISTS, только новые имена)
    --slovar           пересчитать словарь по signals + proekt_uliki
    --proba-arhiv [N]  ПРОБА ПРИБОРА: прогнать N архивных сигналов через приём потока
    --chisla           числа по собранному
    --kontrol          склейки текстами рядом + контроли с заведомо негодным входом
    --baza PATH        другая база (для отладки в песочнице)
    --suho             ничего не писать в базу
"""
import collections
import datetime
import io
import json
import os
import random
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r'C:\sender\_ops')
try:
    import p3_proekt_lib as L
except ImportError:
    import importlib
    L = importlib.import_module('3s_p3_proekt_lib')

BAZA = r'C:\sender\enrich.db'

SHEMA = [
    """CREATE TABLE IF NOT EXISTS proekty (
        proekt_id TEXT PRIMARY KEY,
        inn TEXT, zakazchik TEXT, zakazchik_iz TEXT,
        otrasl TEXT, otrasl_prior INTEGER, otrasl_iz TEXT,
        region TEXT, region_iz TEXT, mesto TEXT, adres TEXT,
        obekt TEXT, tip_rabot TEXT,
        stadiya TEXT, stadiya_kod INTEGER, stadiya_data TEXT, stadiya_iz TEXT,
        stadiya_rannyaya INTEGER,
        ts TEXT, data_pervaya TEXT, data_poslednyaya TEXT, gody_iz_teksta TEXT,
        sum TEXT, summa_rub REAL, hotness TEXT,
        zontik INTEGER, ulik INTEGER, istochnikov INTEGER, istochniki TEXT,
        event_types TEXT, klyuch_sostav TEXT,
        yakorya TEXT, goroda TEXT, regiony TEXT, raboty TEXT,
        sklejka_prichiny TEXT, created_at TEXT, updated_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS proekt_uliki (
        ulika_id TEXT PRIMARY KEY,
        proekt_id TEXT, inn TEXT, source TEXT, source_url TEXT, citata TEXT,
        event_type TEXT, sum TEXT, hotness TEXT,
        stadiya TEXT, stadiya_kod INTEGER, otrasl TEXT,
        ts TEXT, data_sobytiya TEXT, data_vzyatiya TEXT,
        goroda TEXT, regiony TEXT, yakorya TEXT, raboty TEXT,
        inn_conf TEXT, suspect TEXT, signal_rowid INTEGER,
        prichina TEXT, added_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS proekt_slovar (
        osnova TEXT PRIMARY KEY, df INTEGER, zagl INTEGER, stroch INTEGER, forma TEXT)""",
    """CREATE TABLE IF NOT EXISTS proekt_gashenie (
        inn TEXT, osnova TEXT, dolya REAL, PRIMARY KEY (inn, osnova))""",
    "CREATE INDEX IF NOT EXISTS ix_proekty_inn ON proekty(inn)",
    "CREATE INDEX IF NOT EXISTS ix_uliki_proekt ON proekt_uliki(proekt_id)",
    "CREATE INDEX IF NOT EXISTS ix_uliki_inn ON proekt_uliki(inn)",
]

SEYCHAS = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
_FORMY = {}


def otkryt(put, zapis):
    if zapis:
        con = sqlite3.connect(put, timeout=60)
        con.execute('PRAGMA busy_timeout=60000')
    else:
        con = sqlite3.connect('file:%s?mode=ro' % put.replace('\\', '/'), uri=True)
    con.row_factory = sqlite3.Row
    return con


def sozdat_tablicy(con):
    est = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    novye = [t for t in ('proekty', 'proekt_uliki', 'proekt_slovar', 'proekt_gashenie')
             if t not in est]
    for s in SHEMA:
        con.execute(s)
    con.commit()
    return novye


# ───────────────────────────────────────────────────────── корпусный словарь
def perechitat_slovar(con, con_w):
    """df основы, доля заглавных и самая частая форма написания. Считается по тем же
    текстам, что лежат в signals и в уже собранных уликах."""
    df, zagl, stroch = collections.Counter(), collections.Counter(), collections.Counter()
    forma = collections.defaultdict(collections.Counter)
    n = 0
    teksty = [(r[0] or '') + ' ' + (r[1] or '')
              for r in con.execute('select what, event_type from signals')]
    # корпус словаря — ИМЕННО signals: цитаты улик это те же тексты, и их подмешивание
    # удвоило бы счёт слов после первого же перелива.
    for t in teksty:
        n += 1
        vid = set()
        for w in L.SLOVO.findall(t):
            o = L.osnova(w)
            vid.add(o)
            if w[0].isupper():
                zagl[o] += 1
                forma[o][w] += 1
            else:
                stroch[o] += 1
        for o in vid:
            df[o] += 1
    con_w.execute('delete from proekt_slovar')
    con_w.executemany('insert or replace into proekt_slovar values (?,?,?,?,?)',
                      [(o, df[o], zagl.get(o, 0), stroch.get(o, 0),
                        (forma[o].most_common(1)[0][0] if forma.get(o) else o))
                       for o in df])
    # гашение: якорь, стоящий в половине и более сигналов одного ИНН, различать не может
    po_inn = collections.defaultdict(list)
    for r in con.execute('select inn, what, event_type from signals'):
        po_inn[(r[0] or '').strip()].append((r[1] or '') + ' ' + (r[2] or ''))
    gash = []
    slov = {'df': df, 'zagl': zagl, 'stroch': stroch}
    for inn, tt in po_inn.items():
        if len(tt) < 4:
            continue
        c = collections.Counter()
        for t in tt:
            c.update(yakorya_teksta(t, slov))
        for o, k in c.items():
            if k >= L.DOLYA_V_INN * len(tt):
                gash.append((inn, o, k / float(len(tt))))
    con_w.execute('delete from proekt_gashenie')
    con_w.executemany('insert or replace into proekt_gashenie values (?,?,?)', gash)
    con_w.commit()
    return n, len(df), len(gash)


def zagruzit_slovar(con):
    df, zagl, stroch, forma = {}, {}, {}, {}
    for r in con.execute('select osnova, df, zagl, stroch, forma from proekt_slovar'):
        df[r[0]] = r[1]
        zagl[r[0]] = r[2]
        stroch[r[0]] = r[3]
        forma[r[0]] = r[4]
    gash = collections.defaultdict(set)
    for r in con.execute('select inn, osnova from proekt_gashenie'):
        gash[r[0]].add(r[1])
    _FORMY.update(forma)     # чтобы «объект» писался «Тайшет», а не основой «тайшет»
    return {'df': df, 'zagl': zagl, 'stroch': stroch, 'forma': forma, 'gash': gash}


def imya_sobstvennoe(o, slov):
    z, s = slov['zagl'].get(o, 0), slov['stroch'].get(o, 0)
    return (z + s) > 0 and z / float(z + s) >= 0.6


def yakorya_teksta(t, slov):
    """Якоря по тексту: имена собственные с различающей силой."""
    p = L.razobrat_signal({'what': t, 'event_type': ''})
    return yakorya(p, slov)


def yakorya(p, slov):
    kand = set(p['yakorya_kand']) | set(p['zaglavnye'])
    kand |= {L.osnova(g) for g in p['goroda']}
    kand |= {L.osnova(r.split()[0]) for r in p['regiony']}
    out = set()
    for o in kand:
        if len(o) < 3 or o in L.STOP_OSNOVY or o in L.PRAVOVYE:
            continue
        if any(o.startswith(m[:4]) for m in L.MESYACY):
            continue
        if slov['df'].get(o, 0) > L.DF_OBSHCHIY:
            continue
        if o.isalpha() and len(o) <= 7 and o.upper() == o:
            out.add(o)
            continue
        if imya_sobstvennoe(o, slov):
            out.add(o)
    return out


def priznaki(row, slov):
    """Сигнал -> признаки, готовые к сравнению. Одинаково для архива и для потока."""
    p = L.razobrat_signal(row)
    p['yak'] = yakorya(p, slov) - slov['gash'].get((p['inn'] or '').strip(), set())
    p['zontik'] = (len(p['goroda']) + len(p['regiony'])) >= L.ZONTIK_MEST
    p['df'] = slov['df']
    return p


def _ryad(con):
    """Курсор, отдающий строки по ИМЕНИ колонки, независимо от настроек вызывающего.

    Так точка входа не требует от коллектора ставить `row_factory`: без этого
    `dict(строка)` и `u['goroda']` молча падали бы уже внутри живого конвейера."""
    cur = con.cursor()
    cur.row_factory = sqlite3.Row
    return cur


# ─────────────────────────────────────────────── предикаты склейки (заслоны)
def _yak_ob(d):
    """Якоря БЕЗ топонимов: собственно объект, а не место. Общий город доказывает
    место, но не проект — на площадке предприятия их бывает несколько."""
    mesta = {L.osnova(g) for g in d['goroda']}
    mesta |= {L.osnova(r.split()[0]) for r in d['regiony']}
    return d['yak'] - mesta


def protivorechie(a, b):
    ao, bo = _yak_ob(a), _yak_ob(b)
    if ao and bo and not (ao & bo):
        return 'объекты разные: %s / %s' % (','.join(sorted(ao)[:3]),
                                            ','.join(sorted(bo)[:3]))
    if a['goroda'] and b['goroda'] and not (a['goroda'] & b['goroda']):
        return 'города разные'
    if a['regiony'] and b['regiony'] and not (a['regiony'] & b['regiony']):
        return 'регионы разные'
    if a['data'] and b['data'] and abs((a['data'] - b['data']).days) > L.OKNO_DNEY:
        return 'даты далеко'
    if bool(a['zontik']) != bool(b['zontik']):
        return 'зонтичный против площадочного'
    return ''


def svyaz(a, b):
    sh = L.zhakkar(a['shingly'], b['shingly'])
    if sh >= L.SHOZHEST_DUBL:
        return 3, 'тексты совпали на %.2f' % sh
    ob = a['yak'] & b['yak']
    mesta = (a['goroda'] & b['goroda']) | (a['regiony'] & b['regiony'])
    rab = a['raboty'] & b['raboty']
    if len(ob) >= 2:
        return 3, 'общие имена: %s' % ', '.join(sorted(ob)[:4])
    if len(ob) == 1:
        o = list(ob)[0]
        if a['df'].get(o, 0) <= 15:
            return 2, 'редкое общее имя: %s (в корпусе %d)' % (o, a['df'].get(o, 0))
        if rab:
            return 2, 'общее имя %s + работы: %s' % (o, ', '.join(sorted(rab)))
        if sh >= L.SHOZHEST_SLAB:
            return 2, 'общее имя %s + сходство %.2f' % (o, sh)
    if mesta and rab:
        return 2, 'место %s + работы %s' % (', '.join(sorted(mesta)),
                                            ', '.join(sorted(rab)))
    if mesta and sh >= L.SHOZHEST_SLAB:
        return 1, 'место %s + сходство %.2f' % (', '.join(sorted(mesta)), sh)
    return 0, ''


def ulika_v_priznaki(u):
    """Улика из базы -> те же признаки, что у свежего сигнала. Без повторного разбора:
    места, якоря и работы лежат в строке улики, текст цитаты хранится целиком."""
    d = {'goroda': set(filter(None, (u['goroda'] or '').split(','))),
         'regiony': set(filter(None, (u['regiony'] or '').split(','))),
         'yak': set(filter(None, (u['yakorya'] or '').split(','))),
         'raboty': set(filter(None, (u['raboty'] or '').split(','))),
         'shingly': L.shingly(u['citata'] or ''),
         'data': L.razobrat_ts(u['data_sobytiya'] or ''),
         'zontik': 0, 'stadiya_kod': u['stadiya_kod'] or 6}
    d['zontik'] = (len(d['goroda']) + len(d['regiony'])) >= L.ZONTIK_MEST
    return d


# ─────────────────────────────────────────────────────── ПРИЁМ СОБЫТИЯ
def prinyat_sobytie(con, row, slov, imena=None, pisat=True, kesh=None):
    """Пришло событие -> нашёлся проект (добавили улику) либо завели новый.

    `row`: dict в колонках signals. Возвращает (proekt_id, что_сделано, причина).
    Идемпотентно: то же доказательство второй раз не удваивается."""
    p = priznaki(row, slov)
    p['df'] = slov['df']
    inn = (row.get('inn') or '').strip()
    uid = L.klyuch_uliki(row.get('source'), row.get('source_url'), row.get('what'))

    if pisat:
        est = con.execute('select proekt_id from proekt_uliki where ulika_id=?',
                          (uid,)).fetchone()
        if est:
            return est[0], 'уже было', 'то же доказательство'

    # кандидаты: проекты этого ИНН вместе с их уликами
    if kesh is not None and inn in kesh:
        kand = kesh[inn]
    else:
        kand = []
        for pr in _ryad(con).execute('select * from proekty where inn=?', (inn,)):
            ul = [ulika_v_priznaki(u) for u in _ryad(con).execute(
                'select * from proekt_uliki where proekt_id=?', (pr['proekt_id'],))]
            kand.append({'row': dict(pr), 'chleny': ul})
        if kesh is not None:
            kesh[inn] = kand

    cel, prich, sila = None, '', 0
    for k in kand:
        if any(protivorechie(p, m) for m in k['chleny']):
            continue
        s_max, pr_max = 0, ''
        for m in k['chleny']:
            s, pr = svyaz(p, m)
            if s > s_max:
                s_max, pr_max = s, pr
        if s_max > sila:
            cel, prich, sila = k, pr_max, s_max
    if cel is not None:
        pid = cel['row']['proekt_id']
        chto = 'дополнен'
    else:
        mesto = ' | '.join(sorted(p['goroda'])[:3])
        region = ' | '.join(sorted(p['regiony'])[:2])
        obekt = ' '.join(sorted(p['yak'])[:4])
        rabota = ' | '.join(sorted(p['raboty'])[:2])
        pid, sostav = L.klyuch_proekta(inn, mesto or region, obekt, rabota)
        zanyat = {k['row']['proekt_id'] for k in kand}
        baza_id, i = pid, 1
        while pid in zanyat:          # разные дела с одинаковыми якорями: -2, -3, …
            i += 1
            pid = '%s-%d' % (baza_id, i)
        chto, prich = 'новый', 'ни один проект ИНН не подошёл'
        cel = {'row': {'proekt_id': pid, 'klyuch_sostav': sostav, 'created_at': SEYCHAS},
               'chleny': []}
        kand.append(cel)

    cel['chleny'].append({'goroda': p['goroda'], 'regiony': p['regiony'], 'yak': p['yak'],
                          'raboty': p['raboty'], 'shingly': p['shingly'],
                          'data': p['data'], 'zontik': p['zontik'],
                          'stadiya_kod': p['stadiya_kod']})
    if pisat:
        zapisat_uliku(con, pid, row, p, uid, prich)
        peresobrat_kartochku(con, pid, cel['row'].get('klyuch_sostav', ''),
                             cel['row'].get('created_at', SEYCHAS),
                             imena if imena is not None else _imya_odnogo(con, inn))
    return pid, chto, prich


_KESH_IMEN = {}


def _imya_odnogo(con, inn):
    """Название заказчика по одному ИНН — чтобы поток не обязан был знать про
    `companies`. Пакетный прогон передаёт готовый словарь и сюда не заходит."""
    if inn in _KESH_IMEN:
        return _KESH_IMEN[inn]
    d = {'name': '', 'region': '', 'adres': '', 'otkuda': ''}
    for tabl, k_name, k_reg, k_adr in (('companies', 'name', 'region', None),
                                       ('requisites', 'name_short', None, 'address')):
        try:
            sel = ','.join(c for c in (k_name, k_reg, k_adr) if c)
            r = _ryad(con).execute('select %s from %s where inn=? limit 1'
                                   % (sel, tabl), (inn,)).fetchone()
        except sqlite3.Error:
            continue
        if r and r[k_name] and not d['name']:
            d['name'] = str(r[k_name])[:160]
            d['otkuda'] = tabl + '.' + k_name
        if r and k_reg and r[k_reg] and not d['region']:
            d['region'] = str(r[k_reg])[:80]
        if r and k_adr and r[k_adr] and not d['adres']:
            d['adres'] = str(r[k_adr])[:200]
    _KESH_IMEN[inn] = {inn: d}
    return _KESH_IMEN[inn]


def zapisat_uliku(con, pid, row, p, uid, prich):
    con.execute(
        'insert or ignore into proekt_uliki values '
        '(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (uid, pid, (row.get('inn') or '').strip(), row.get('source') or '',
         row.get('source_url') or '', row.get('what') or '', row.get('event_type') or '',
         row.get('sum') or '', str(row.get('hotness') or ''), p['stadiya'],
         p['stadiya_kod'], ' | '.join(p['otrasli']), row.get('ts') or '',
         str(p['data']) if p['data'] else '', row.get('updated_at') or '',
         ','.join(sorted(p['goroda'])), ','.join(sorted(p['regiony'])),
         ','.join(sorted(p['yak'])), ','.join(sorted(p['raboty'])),
         row.get('inn_conf') or '', str(row.get('suspect') or ''),
         row.get('_rid') or None, prich, SEYCHAS))


def peresobrat_kartochku(con, pid, sostav, created, imena):
    """Карточка проекта пересобирается из ВСЕХ его улик. Ничего не перезаписывается
    молча: источники складываются, их число стоит рядом."""
    ul = list(_ryad(con).execute('select * from proekt_uliki where proekt_id=?', (pid,)))
    if not ul:
        return
    gor, reg, rab, otr, yak = (collections.Counter() for _ in range(5))
    ist, sob = [], []
    prior = 0
    for u in ul:
        gor.update(filter(None, (u['goroda'] or '').split(',')))
        reg.update(filter(None, (u['regiony'] or '').split(',')))
        rab.update(filter(None, (u['raboty'] or '').split(',')))
        yak.update(filter(None, (u['yakorya'] or '').split(',')))
        for o in filter(None, [x.strip() for x in (u['otrasl'] or '').split('|')]):
            otr[o] += 1
            if o in PRIOR_OTRASLI:
                prior = 1
        if u['source'] and u['source'] not in ist:
            ist.append(u['source'])
        if u['event_type']:
            sob.append(u['event_type'])
    daty = sorted(filter(None, (u['data_sobytiya'] for u in ul)))
    summy = [L.summa_v_rub(u['sum']) for u in ul]
    summy = [s for s in summy if s]
    if daty:
        pozdn = max(ul, key=lambda u: u['data_sobytiya'] or '')
    else:
        pozdn = max(ul, key=lambda u: u['stadiya_kod'] or 0)
    inn = ul[0]['inn']
    im = imena.get(inn, {})
    gody = sorted({g for u in ul for g in
                   __import__('re').findall(r'\b20[0-3]\d\b', u['citata'] or '')})
    con.execute(
        'insert or replace into proekty values '
        '(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (pid, inn, im.get('name', ''), im.get('otkuda', ''),
         ' | '.join(o for o, _ in otr.most_common(3)), prior,
         ' ; '.join('%s — по %d уликам из %d' % (o, c, len(ul))
                    for o, c in otr.most_common(3)),
         ' | '.join(r for r, _ in reg.most_common(2)),
         'текст улик' if reg else ('регистрация по ИНН' if im.get('region') else ''),
         ' | '.join(g for g, _ in gor.most_common(3)), im.get('adres', ''),
         ' '.join(_forma(o) for o, c in yak.most_common()
                  if c >= (1 if len(ul) == 1 else max(2, len(ul) // 2)))[:120],
         ' | '.join(r for r, _ in rab.most_common(2)),
         pozdn['stadiya'], pozdn['stadiya_kod'], daty[-1] if daty else '',
         (pozdn['source'] or '') + ' ' + (pozdn['source_url'] or '')[:150],
         min((u['stadiya_kod'] or 9) for u in ul),
         daty[-1] if daty else '', daty[0] if daty else '', daty[-1] if daty else '',
         ','.join(gody),
         ' | '.join(sorted({u['sum'] for u in ul if u['sum']}))[:300],
         max(summy) if summy else None,
         max([int(u['hotness']) for u in ul if str(u['hotness']).isdigit()] or [0]),
         1 if (len(gor) + len(reg)) >= L.ZONTIK_MEST else 0,
         len(ul), len(ist), ' | '.join(ist)[:900],
         ' | '.join(sorted(set(sob)))[:200], sostav,
         ','.join(o for o, _ in yak.most_common(12)),
         ','.join(sorted(gor)), ','.join(sorted(reg)), ','.join(sorted(rab)),
         ' ;; '.join(filter(None, (u['prichina'] for u in ul)))[:900],
         created, SEYCHAS))


PRIOR_OTRASLI = {n for n, p, _ in L.OTRASLI if p}


def _forma(o):
    return _FORMY.get(o, o)


# ───────────────────────────────────────────────────── имена заказчиков
def imena_kompaniy(con):
    """Название/регион/адрес по ИНН. Колонки не угадываются: таблицы осматриваются,
    найденное печатается."""
    out = {}
    for tabl in ('companies', 'requisites', 'base_ref'):
        try:
            kol = [r[1] for r in con.execute('pragma table_info(%s)' % tabl)]
        except sqlite3.Error:
            continue
        if not kol:
            continue
        if 'inn' not in kol:
            print('  %s: колонки %s — ИНН нет, пропуск' % (tabl, ','.join(kol[:12])))
            continue
        k_name = [c for c in kol if c.lower() in
                  ('name', 'company', 'title', 'short_name', 'name_short', 'org',
                   'company_name', 'nazvanie', 'full_name', 'org_name')]
        k_reg = [c for c in kol if 'region' in c.lower() or c.lower() == 'subject']
        k_adr = [c for c in kol if 'addr' in c.lower() or 'adres' in c.lower()]
        print('  %s: колонки %s ; имя=%s регион=%s адрес=%s'
              % (tabl, ','.join(kol[:14]), k_name[:1], k_reg[:1], k_adr[:1]))
        if not (k_name or k_reg or k_adr):
            continue
        sel = ['inn'] + k_name[:1] + k_reg[:1] + k_adr[:1]
        vz = 0
        for r in con.execute('select %s from %s' % (','.join(sel), tabl)):
            i = (r['inn'] or '').strip()
            if not i:
                continue
            d = out.setdefault(i, {'name': '', 'region': '', 'adres': '', 'otkuda': ''})
            if k_name and not d['name'] and r[k_name[0]]:
                d['name'] = str(r[k_name[0]])[:160]
                d['otkuda'] = tabl + '.' + k_name[0]
                vz += 1
            if k_reg and not d['region'] and r[k_reg[0]]:
                d['region'] = str(r[k_reg[0]])[:80]
            if k_adr and not d['adres'] and r[k_adr[0]]:
                d['adres'] = str(r[k_adr[0]])[:200]
        print('    имён взято: %d' % vz)
    return out


# ───────────────────────────────────────────────────── контроли и числа
def kontrol_negodnym(slov):
    """Ноль доказывается так же тщательно, как находка: у каждого признака свой
    заведомо негодный вход."""
    itog = []

    def sob(inn, what, ts='', et='модернизация', src='x.ru', rid=0):
        return {'_rid': rid, 'inn': inn, 'source': src, 'what': what, 'event_type': et,
                'source_url': 'http://%s/%d' % (src, rid), 'sum': '', 'hotness': '3',
                'ts': ts, 'updated_at': '2026-01-01', 'suspect': '0', 'inn_conf': ''}

    def skolko(rows):
        con = sqlite3.connect(':memory:')
        con.row_factory = sqlite3.Row
        sozdat_tablicy(con)
        kesh = {}
        for r in rows:
            prinyat_sobytie(con, r, slov, {}, True, kesh)
        return con.execute('select count(*) from proekty').fetchone()[0]

    proby = [
        ('одно предприятие, РАЗНЫЕ города — склейки быть не должно',
         [sob('1', 'Модернизация газоочистки на заводе в Братске', rid=1),
          sob('1', 'Модернизация газоочистки на заводе в Волгограде', rid=2)], 2),
        ('одно предприятие, одно место и объект — склейка обязана быть',
         [sob('2', 'В Тайшете строится Тайшетский алюминиевый завод, монтаж газоочистки',
              rid=3),
          sob('2', 'Тайшетский алюминиевый завод в Тайшете: пусконаладка газоочистки',
              rid=4)], 1),
        ('разрыв дат больше окна — склейки быть не должно',
         [sob('3', 'В Тайшете строится Тайшетский алюминиевый завод, монтаж газоочистки',
              ts='2019-01-10', rid=5),
          sob('3', 'В Тайшете Тайшетский алюминиевый завод: монтаж газоочистки',
              ts='2026-01-10', rid=6)], 2),
        ('пустые тексты — не должны слипаться в один проект-помойку',
         [sob('4', '', rid=7 + i, src='s%d.ru' % i) for i in range(5)], 5),
        ('одно место, но РАЗНЫЕ названные объекты — склейки быть не должно',
         [sob('8', 'В Тобольске отработаны пусковые режимы Амурского ГХК на пилотной '
                   'площадке, моделирование запуска линии полиэтилена', rid=30),
          sob('8', 'В Тобольске идёт реконструкция компрессорного блока подачи водорода '
                   'на площадке ЗапСиб по проекту технического перевооружения', rid=31)],
         2),
        ('РАЗНЫЕ ИНН с одинаковым текстом — общего проекта быть не должно',
         [sob('5', 'В Тайшете строится алюминиевый завод, монтаж газоочистки', rid=20),
          sob('6', 'В Тайшете строится алюминиевый завод, монтаж газоочистки', rid=21)],
         2),
        ('то же доказательство дважды — второй раз не должен ничего добавить',
         [sob('7', 'В Тайшете строится алюминиевый завод', rid=22),
          sob('7', 'В Тайшете строится алюминиевый завод', rid=22)], 1),
    ]
    for imya, rows, zhd in proby:
        vyshlo = skolko(rows)
        itog.append((imya, zhd, vyshlo, vyshlo == zhd))
        print('  %-62s ждём %d вышло %d  %s'
              % (imya[:62], zhd, vyshlo, 'ВЕРНО' if vyshlo == zhd else 'НЕВЕРНО'))

    # места: заведомо негодный вход не должен давать ни одного места
    mus = ('Компрессор винтовой ВК-15 подаёт 2,5 куб. м в минуту при давлении 8 бар, '
           'замена фильтров и масла раз в 4000 часов по регламенту.')
    p = L.razobrat_signal({'what': mus, 'event_type': ''})
    ok = not p['goroda'] and not p['regiony']
    print('  %-62s ждём 0 вышло %d  %s' % ('текст без места: городов+регионов', 0,
                                           len(p['goroda']) + len(p['regiony'])) if False
          else '  %-62s ждём 0 вышло %d  %s'
          % ('мусорный текст: мест не должно быть', len(p['goroda']) + len(p['regiony']),
             'ВЕРНО' if ok else 'НЕВЕРНО ' + str(p['goroda'] | p['regiony'])))
    itog.append(('мусорный текст без мест', 0, len(p['goroda']) + len(p['regiony']), ok))
    # ловушки, на которых прибор уже врал
    lovushki = [('строятся два новых корпуса электролиза', set()),
                ('запущена клинкерная линия цементного завода', set()),
                ('в городе Тайшет Иркутской области', {'Тайшет'}),
                ('в Каменске-Уральском на УАЗе', {'Каменск-Уральский'}),
                ('свободный доступ к октябрьским данным', set()),
                ('ДКС на Северо-Комсомольском месторождении в ЯНАО', set()),
                ('НПЗ в Комсомольске-на-Амуре', {'Комсомольск-на-Амуре'}),
                ('ГОК на Черногорском месторождении в Норильском районе',
                 {'Норильск'}),
                ('завод в городе Черногорск', {'Черногорск'})]
    for t, zhd in lovushki:
        p = L.razobrat_signal({'what': t, 'event_type': ''})
        ok = p['goroda'] == zhd
        print('  ловушка «%s» -> %s %s' % (t[:44], sorted(p['goroda']) or '—',
                                           'ВЕРНО' if ok else 'НЕВЕРНО, ждали %s' % zhd))
        itog.append((t, len(zhd), len(p['goroda']), ok))
    # регион: ловушки, на которых прибор уже врал
    reg_lov = [('ОЭЗ «Новоорловская» в Приморском районе Санкт-Петербурга',
                {'Санкт-Петербург'}),
               ('северная площадка предприятия', set()),
               ('Ямало-Ненецкий автономный округ, Новый Уренгой', {'ЯНАО'}),
               ('завод в ЯНАО', {'ЯНАО'}),
               ('Комсомольский НПЗ в Комсомольске-на-Амуре', set()),
               ('в Красноярском крае построят завод', {'Красноярский край'})]
    for t, zhd in reg_lov:
        p = L.razobrat_signal({'what': t, 'event_type': ''})
        ok = p['regiony'] == zhd
        print('  регион «%s» -> %s %s' % (t[:40], sorted(p['regiony']) or '—',
                                          'ВЕРНО' if ok else 'НЕВЕРНО, ждали %s' % zhd))
        itog.append((t, len(zhd), len(p['regiony']), ok))
    # отрасль: заведомо негодный вход
    p = L.razobrat_signal({'what': 'Компания открыла новый офис продаж и склад запчастей',
                           'event_type': ''})
    ok = p['otrasl_prior'] == 0
    print('  отрасль у офиса продаж: приоритет %d  %s'
          % (p['otrasl_prior'], 'ВЕРНО' if ok else 'НЕВЕРНО'))
    itog.append(('отрасль офиса', 0, p['otrasl_prior'], ok))
    p = L.razobrat_signal({'what': 'Строительство цементного завода и клинкерной линии',
                           'event_type': ''})
    ok = 'цементная' in p['otrasli']
    print('  отрасль у цементного завода: %s  %s'
          % (p['otrasli'][:2], 'ВЕРНО' if ok else 'НЕВЕРНО'))
    itog.append(('отрасль цемента', 1, 1 if ok else 0, ok))
    return itog


def chisla(con):
    n_p = con.execute('select count(*) from proekty').fetchone()[0]
    n_u = con.execute('select count(*) from proekt_uliki').fetchone()[0]
    podt = con.execute('select count(*) from proekty where istochnikov>=2').fetchone()[0]
    odin = con.execute('select count(*) from proekty where ulik=1').fetchone()[0]
    mnogo = con.execute('select count(*) from proekty where ulik>1').fetchone()[0]
    inn = con.execute('select count(distinct inn) from proekty').fetchone()[0]
    zont = con.execute('select count(*) from proekty where zontik=1').fetchone()[0]
    prior = con.execute('select count(*) from proekty where otrasl_prior=1').fetchone()[0]
    smesto = con.execute("select count(*) from proekty where mesto<>''").fetchone()[0]
    sreg = con.execute("select count(*) from proekty where region<>''").fetchone()[0]
    sdata = con.execute("select count(*) from proekty where stadiya_data<>''").fetchone()[0]
    ssum = con.execute('select count(*) from proekty where summa_rub is not null'
                       ).fetchone()[0]
    print('\n########## ЧИСЛА ПО СОБРАННОМУ')
    print('  улик в базе                   %5d' % n_u)
    print('  ПРОЕКТОВ                      %5d' % n_p)
    print('  разных ИНН                    %5d' % inn)
    print('  подтверждены 2+ источниками   %5d' % podt)
    print('  одиночных (1 улика)           %5d' % odin)
    print('  с 2+ уликами                  %5d' % mnogo)
    print('  зонтичных (программа, не площадка) %d' % zont)
    print('  приоритетная отрасль          %5d' % prior)
    print('  есть место / регион / дата / сумма   %d / %d / %d / %d'
          % (smesto, sreg, sdata, ssum))
    r = con.execute('select stadiya, count(*) c from proekty group by 1 order by c desc'
                    ).fetchall()
    print('  стадии: %s' % ' | '.join('%s=%d' % (x[0], x[1]) for x in r[:9]))
    r = con.execute('select otrasl, count(*) c from proekty group by 1 order by c desc '
                    'limit 8').fetchall()
    print('  отрасли: %s' % ' | '.join('%s=%d' % ((x[0] or '∅')[:26], x[1]) for x in r))
    r = con.execute('select ulik, count(*) c from proekty group by 1 order by ulik'
                    ).fetchall()
    print('  размеры проектов: %s' % ' '.join('%d:%d' % (x[0], x[1]) for x in r[:14]))
    return n_p, podt, odin


def kontrol_skleek(con, skolko_pok=10):
    print('=' * 74)
    print('КОНТРОЛЬ 1: ИНН с наибольшим числом сигналов — во сколько проектов разошлись')
    print('=' * 74)
    top = con.execute('select inn, count(*) c from proekt_uliki group by 1 '
                      'order by c desc limit 6').fetchall()
    for inn, c in top:
        pr = list(con.execute('select * from proekty where inn=? order by ulik desc',
                              (inn,)))
        ist = con.execute('select count(distinct source) from proekt_uliki where inn=?',
                          (inn,)).fetchone()[0]
        print('ИНН %s: улик %d из %d источников -> ПРОЕКТОВ %d ; размеры %s'
              % (inn, c, ist, len(pr), [x['ulik'] for x in pr][:24]))
        for x in pr[:10]:
            print('   [%2d улик/%2d ист] %-24s %-24s %s'
                  % (x['ulik'], x['istochnikov'], (x['mesto'] or x['region'] or '—')[:24],
                     (x['obekt'] or '—')[:24], (x['tip_rabot'] or '—')[:30]))
    print()
    print('=' * 74)
    print('КОНТРОЛЬ 2: СКЛЕЙКИ ТЕКСТАМИ РЯДОМ — смотреть глазами')
    print('=' * 74)
    sk = list(con.execute('select * from proekty where ulik>=2 order by random() limit ?',
                          (skolko_pok,)))
    for p in sk:
        print('-' * 74)
        print('%s ИНН %s улик %d источников %d | место=%s | объект=%s | стадия=%s'
              % (p['proekt_id'], p['inn'], p['ulik'], p['istochnikov'],
                 p['mesto'] or p['region'] or '—', p['obekt'] or '—', p['stadiya']))
        print('  почему слиплись: %s' % (p['sklejka_prichiny'] or '—')[:260])
        for u in con.execute('select * from proekt_uliki where proekt_id=? limit 5',
                             (p['proekt_id'],)):
            print('  · %-20s %-15s %s' % ((u['source'] or '')[:20],
                                          (u['event_type'] or '')[:15],
                                          (u['data_sobytiya'] or '')[:10]))
            print('      %s' % (u['citata'] or '').replace('\n', ' ')[:300])
    print()
    b = con.execute('select * from proekty order by ulik desc limit 1').fetchone()
    print('=' * 74)
    print('КОНТРОЛЬ 3: САМЫЙ БОЛЬШОЙ ПРОЕКТ ЦЕЛИКОМ (%d улик, ИНН %s, место %s)'
          % (b['ulik'], b['inn'], b['mesto'] or '—'))
    print('=' * 74)
    for u in con.execute('select * from proekt_uliki where proekt_id=?',
                         (b['proekt_id'],)):
        print('  · %-20s %s' % ((u['source'] or '')[:20],
                                (u['citata'] or '').replace('\n', ' ')[:230]))


# ───────────────────────────────────── где в живом конвейере звать приём
def tochka_vhoda():
    """Где в живом конвейере рождается сигнал. Точку вызова не выдумываем, а показываем
    строкой файла. Первый поиск (только «insert into signals» в C:\\sender\\*.py) дал НОЛЬ —
    значит искали не то: смотрим подпапки и любые обращения к таблице на запись."""
    import re as _re
    zapis = _re.compile(r"(insert|replace|update|executemany|upsert|add_signal|"
                        r"save_signal|into)\s*[^\n]{0,40}signals", _re.I)
    upom = _re.compile(r"['\"]signals['\"]|\bsignals\b", _re.I)
    fayly, mest = [], 0
    for koren, papki, imena in os.walk(r'C:\sender'):
        papki[:] = [d for d in papki if d.lower() not in
                    ('__pycache__', 'node_modules', '.git', 'venv', '_ops', 'logs')]
        if koren.count(os.sep) > 4:
            papki[:] = []
        for im in imena:
            if not im.endswith('.py'):
                continue
            f = os.path.join(koren, im)
            try:
                stroki = io.open(f, encoding='utf-8', errors='replace').read().splitlines()
            except OSError:
                continue
            n_up = sum(1 for x in stroki if upom.search(x))
            if not n_up:
                continue
            zap = [(i, x) for i, x in enumerate(stroki, 1) if zapis.search(x)]
            fayly.append((os.path.relpath(f, r'C:\sender'), n_up, len(zap)))
            for i, x in zap[:3]:
                mest += 1
                print('  ЗАПИСЬ %s:%d  %s' % (os.path.relpath(f, r'C:\sender'), i,
                                              x.strip()[:100]))
    fayly.sort(key=lambda z: -z[1])
    print('  файлов, упоминающих signals: %d' % len(fayly))
    for f, n_up, n_z in fayly[:10]:
        print('    %-36s упоминаний %3d, строк записи %d' % (f[:36], n_up, n_z))
    print('  мест записи в signals найдено: %d' % mest)
    return mest


def vylozhit(f):
    try:
        import urllib.request
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        rq = urllib.request.Request(
            '%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'), os.path.basename(f)),
            data=io.open(f, 'rb').read(), method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
        print('  дроп %s: %s' % (os.path.basename(f),
                                 op.open(rq, timeout=300).read()
                                 .decode('utf-8', 'replace')[:80]))
    except Exception as e:  # noqa: BLE001
        print('  на дроп не выложено: %s' % str(e)[:110])


def chernovik(con):
    """Черновик для показа примеров: CSV проектов и улик в _ops + на дроп.
    Хранилище — база; файлы только чтобы посмотреть глазами."""
    import csv
    for tabl, put in (('proekty', r'C:\sender\_ops\3s_proekty.csv'),
                      ('proekt_uliki', r'C:\sender\_ops\3s_proekt_uliki.csv')):
        rows = list(con.execute('select * from %s' % tabl))
        if not rows:
            continue
        kol = rows[0].keys()
        with io.open(put, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.writer(f, delimiter=';')
            w.writerow(kol)
            for r in rows:
                w.writerow([('' if r[k] is None else str(r[k]).replace('\n', ' '))
                            for k in kol])
        print('  черновик %s: %d строк' % (put, len(rows)))
        vylozhit(put)


class Teh(object):
    """Вывод возвращается ХВОСТОМ, а контроль склейки длинный. Поэтому весь вывод
    пишется в файл и на дроп целиком, а в stdout уходит только выжимка."""

    def __init__(self):
        self.buf = []
        self.staryy = sys.stdout

    def write(self, t):
        self.buf.append(t)

    def flush(self):
        pass

    def vyzhimka(self):
        vse = ''.join(self.buf).splitlines()
        out, propusk = [], False
        for line in vse:
            if 'КОНТРОЛЬ 2' in line or 'КОНТРОЛЬ 3' in line:
                propusk = True
                out.append(line + '  [полностью — в файле на дропе]')
                continue
            if 'КОНТРОЛЬ 4' in line or 'ЧИСЛА' in line or 'КОНТРОЛЬ 1' in line:
                propusk = False
            if not propusk:
                out.append(line)
        return '\n'.join(out)


TABLICY = ('proekty', 'proekt_uliki', 'proekt_slovar', 'proekt_gashenie')


def slit(rab, zhivaya_put, popytok=120, pauza=5, ochistit=False):
    """Перелить готовые таблицы в живую базу ОДНИМ КОРОТКИМ РЫВКОМ.

    Почему так, а не писать в живую по ходу сборки: замер показал, что enrich.db
    занята наглухо — запись не бралась ни за 5, ни за 30, ни за 120 секунд подряд
    (на сервере параллельно работают 8 процессов python, режим журнала откатный, и
    читатели не дают взять исключительную блокировку). Поэтому вся сборка идёт в
    рабочей базе в _ops, а живая база трогается один раз, транзакцией на секунды, и с
    повторами: сколько бы ни было занято, рано или поздно окно найдётся."""
    dannye = {}
    for t in TABLICY:
        rows = [tuple(r) for r in rab.execute('select * from %s' % t)]
        kol = len(rab.execute('select * from %s limit 1' % t).description) if rows else 0
        dannye[t] = (rows, kol)
        print('  готово к переливу %s: %d строк' % (t, len(rows)))
    for i in range(1, popytok + 1):
        try:
            zh = sqlite3.connect(zhivaya_put, timeout=pauza)
            zh.execute('PRAGMA busy_timeout=%d' % (pauza * 1000))
            # окно между читателями короткое: лучше часто пробовать, чем долго ждать
            zh.execute('BEGIN IMMEDIATE')
            for sql in SHEMA:
                zh.execute(sql)
            if ochistit:
                for t_ in TABLICY:            # чистим ТОЛЬКО свои новые таблицы
                    zh.execute('delete from %s' % t_)
            for t in TABLICY:
                rows, kol = dannye[t]
                if not rows:
                    continue
                zh.executemany('insert or replace into %s values (%s)'
                               % (t, ','.join('?' * kol)), rows)
            zh.commit()
            zh.close()
            print('  ПЕРЕЛИТО в живую базу с попытки %d' % i)
            return True
        except sqlite3.Error as e:  # noqa: BLE001
            try:
                zh.close()
            except Exception:  # noqa: BLE001
                pass
            if i % 10 == 0 or i == 1:
                print('  попытка %d: база занята (%s)' % (i, str(e)[:60]))
            time.sleep(pauza)
    print('  НЕ ПЕРЕЛИТО: живая база занята все %d попыток' % popytok)
    return False


# ─────────────────────────────────────────────────────────────── main
def main(argv):
    put = argv[argv.index('--baza') + 1] if '--baza' in argv else BAZA
    rab_put = (argv[argv.index('--rabochaya') + 1] if '--rabochaya' in argv
               else r'C:\sender\_ops\3s_proekty.db')
    suho = '--suho' in argv
    teh = None
    if '--v-fayl' in argv:
        teh = Teh()
        sys.stdout = teh
    if put == rab_put:                       # отладка в песочнице: одна база на всё
        con = otkryt(put, not suho)
        zhivaya = con
    else:
        con = otkryt(rab_put, True)          # рабочая: сюда пишем
        zhivaya = otkryt(put, False)         # живая: только чтение
        print('рабочая база %s ; живая (только чтение) %s' % (rab_put, put))
    if '--zanovo' in argv:          # пересборка с нуля в РАБОЧЕЙ базе (живую не трогает)
        for t_ in ('proekty', 'proekt_uliki', 'proekt_slovar', 'proekt_gashenie'):
            try:
                con.execute('drop table if exists %s' % t_)
            except sqlite3.Error as e:  # noqa: BLE001
                print('  не удалось очистить %s: %s' % (t_, str(e)[:60]))
        con.commit()
        print('рабочая база очищена под пересборку')
    if '--shema' in argv:
        novye = sozdat_tablicy(con)
        print('таблицы созданы (новых: %d) %s' % (len(novye), novye))
    if '--slovar' in argv:
        n, osn, gash = perechitat_slovar(zhivaya, con)
        print('словарь: текстов %d, основ %d, погашенных якорей по ИНН %d'
              % (n, osn, gash))
    slov = zagruzit_slovar(con)
    _FORMY.update(slov['forma'])
    print('словарь загружен: основ %d, ИНН с гашением %d' % (len(slov['df']),
                                                             len(slov['gash'])))
    if '--proba-arhiv' in argv:
        i = argv.index('--proba-arhiv')
        lim = int(argv[i + 1]) if len(argv) > i + 1 and argv[i + 1].isdigit() else 0
        imena = imena_kompaniy(zhivaya)
        rows = [dict(r) for r in zhivaya.execute(
            'select rowid as _rid, * from signals order by updated_at, rowid')]
        if lim:
            rows = rows[:lim]
        itog = collections.Counter()
        kesh = {}
        for k, r in enumerate(rows):
            _, chto, _ = prinyat_sobytie(con, r, slov, imena, True, kesh)
            itog[chto] += 1
            if (k + 1) % 500 == 0:
                con.commit()
                print('  прогнано %d: %s' % (k + 1, dict(itog)))
        con.commit()
        print('ПРОБА НА АРХИВЕ: подано %d, %s' % (len(rows), dict(itog)))
    if '--tochka-vhoda' in argv:
        print('=' * 74)
        print('ГДЕ ЗВАТЬ ПРИЁМ: места вставки сигнала в живых модулях сервера')
        print('=' * 74)
        tochka_vhoda()
    if '--chisla' in argv:
        chisla(con)
    if '--chernovik' in argv:
        chernovik(con)
    if '--slit' in argv:
        print('=' * 74)
        print('ПЕРЕЛИВ В ЖИВУЮ БАЗУ %s' % put)
        print('=' * 74)
        slit(con, put, ochistit='--ochistit' in argv)
    if '--sverka' in argv:
        print('=' * 74)
        print('СВЕРКА ЖИВОЙ БАЗЫ (только чтение, отдельным подключением)')
        print('=' * 74)
        sv = otkryt(put, False)
        tabl = [r[0] for r in sv.execute(
            "select name from sqlite_master where type='table' order by name")]
        print('  таблиц в живой базе: %d' % len(tabl))
        for t_ in TABLICY:
            try:
                print('  %-16s %6d строк' % (t_, sv.execute(
                    'select count(*) from %s' % t_).fetchone()[0]))
            except sqlite3.Error as e:  # noqa: BLE001
                print('  %-16s НЕТ (%s)' % (t_, str(e)[:40]))
        print('  signals (не трогали): %d строк'
              % sv.execute('select count(*) from signals').fetchone()[0])
        try:
            for r in sv.execute('select proekt_id, inn, zakazchik, mesto, stadiya, '
                                'ulik, istochnikov, otrasl from proekty '
                                'order by istochnikov desc limit 3'):
                print('  · %s ИНН %s %s | %s | %s | улик %d ист %d | %s'
                      % (r[0], r[1], (r[2] or '')[:26], (r[3] or '—')[:18], r[4], r[5],
                         r[6], (r[7] or '—')[:28]))
            r = sv.execute('select count(*) from proekt_uliki where citata=\'\'').fetchone()
            print('  улик без цитаты: %d' % r[0])
        except sqlite3.Error as e:  # noqa: BLE001
            print('  выборка не прошла: %s' % str(e)[:60])
        sv.close()
    if '--kontrol' in argv:
        print()
        print('=' * 74)
        print('КОНТРОЛЬ 4: ЗАВЕДОМО НЕГОДНЫЙ ВХОД (ноль доказывается как находка)')
        print('=' * 74)
        it = kontrol_negodnym(slov)
        print('  ИТОГ КОНТРОЛЕЙ: верно %d из %d' % (sum(1 for x in it if x[3]), len(it)))
        kontrol_skleek(con, 10)
    con.close()
    if teh is not None:
        sys.stdout = teh.staryy
        f = r'C:\sender\_ops\3s_proekt_kontrol.txt'
        io.open(f, 'w', encoding='utf-8').write(''.join(teh.buf))
        vylozhit(f)
        print(teh.vyzhimka()[-5200:])


if __name__ == '__main__':
    main(sys.argv[1:])
