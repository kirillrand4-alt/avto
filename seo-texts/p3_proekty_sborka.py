# -*- coding: utf-8 -*-
"""СБОРКА ПРОЕКТОВ из таблицы `signals`. Только чтение исходной базы.

Запуск в песочнице (на выгруженном дампе):
    python3 p3_proekty_sborka.py --lokalno /путь/signals.json [--pokaz]
Запуск на сервере (чтение sqlite, запись результатов в C:\\sender\\_ops\\3s_*):
    python3 zapusk_na_servere.py p3_proekty_sborka.py --pisat

Что делает: разбирает каждый сигнал на якоря (см. p3_proekt_lib), склеивает сигналы
одного ИНН в проекты полным звеном с заслонами, считает числа, печатает контроль.
Ничего в существующие таблицы не пишет.
"""
import collections
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import p3_proekt_lib as L
except ImportError:  # на сервере модуль кладётся с префиксом 3s_
    sys.path.insert(0, r'C:\sender\_ops')
    import importlib
    L = importlib.import_module('3s_p3_proekt_lib') if os.path.exists(
        r'C:\sender\_ops\3s_p3_proekt_lib.py') else None
    if L is None:
        raise


# ─────────────────────────────────────────────────────────────── чтение входа
def chitat(argv):
    if '--lokalno' in argv:
        p = argv[argv.index('--lokalno') + 1]
        return json.load(io.open(p, encoding='utf-8'))
    import sqlite3
    con = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute('select rowid as _rid, * from signals')]


# ───────────────────────────────────────────── корпусная статистика якорей
def statistika(signaly):
    """df основы и доля написаний с заглавной буквы — так имя собственное отличается
    от обычного слова, вместо ручного списка."""
    df = collections.Counter()
    zagl = collections.Counter()
    stroch = collections.Counter()
    for s in signaly:
        vid = set()
        for w in L.SLOVO.findall(s['what'] + ' ' + s['event_type']):
            o = L.osnova(w)
            vid.add(o)
            if w[0].isupper():
                zagl[o] += 1
            else:
                stroch[o] += 1
        for o in vid:
            df[o] += 1
    return df, zagl, stroch


def imya_sobstvennoe(o, zagl, stroch):
    z, s = zagl.get(o, 0), stroch.get(o, 0)
    return (z + s) > 0 and z / float(z + s) >= 0.6


def yakorya(s, df, zagl, stroch):
    """Итоговые якоря сигнала: имена собственные с различающей силой."""
    kand = set(s['yakorya_kand']) | set(s['zaglavnye'])
    kand |= {L.osnova(g) for g in s['goroda']}
    kand |= {L.osnova(r.split()[0]) for r in s['regiony']}
    out = set()
    for o in kand:
        if len(o) < 3 or o in L.STOP_OSNOVY:
            continue
        if any(o.startswith(m[:4]) for m in L.MESYACY):
            continue
        if o in L.PRAVOVYE:
            continue
        if df.get(o, 0) > L.DF_OBSHCHIY:      # слишком часто по всему корпусу
            continue
        if o.isalpha() and len(o) <= 7 and o.upper() == o:
            out.add(o)
            continue
        if imya_sobstvennoe(o, zagl, stroch):
            out.add(o)
    return out


# ──────────────────────────────────────────────────── предикаты склейки
def protivorechie(a, b):
    """Что ЗАПРЕЩАЕТ склейку при любом сходстве. Возвращает причину или ''."""
    if a['goroda'] and b['goroda'] and not (a['goroda'] & b['goroda']):
        return 'города разные: %s / %s' % (','.join(sorted(a['goroda'])),
                                           ','.join(sorted(b['goroda'])))
    if a['regiony'] and b['regiony'] and not (a['regiony'] & b['regiony']):
        return 'регионы разные: %s / %s' % (','.join(sorted(a['regiony'])),
                                            ','.join(sorted(b['regiony'])))
    if a['data'] and b['data'] and abs((a['data'] - b['data']).days) > L.OKNO_DNEY:
        return 'даты далеко: %s / %s' % (a['data'], b['data'])
    if a['zontik'] != b['zontik']:
        return 'зонтичный против площадочного'
    return ''


def svyaz(a, b):
    """Что РАЗРЕШАЕТ склейку. Возвращает (сила, причина) или (0, '')."""
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
        if rab or sh >= L.SHOZHEST_SLAB:
            return 2, 'общее имя %s + %s' % (o, ('работы: ' + ', '.join(sorted(rab)))
                                             if rab else 'сходство %.2f' % sh)
    if mesta and rab:
        return 2, 'место %s + работы %s' % (', '.join(sorted(mesta)),
                                            ', '.join(sorted(rab)))
    if mesta and sh >= L.SHOZHEST_SLAB:
        return 1, 'место %s + сходство %.2f' % (', '.join(sorted(mesta)), sh)
    return 0, ''


def sobrat_proekty(sig):
    """Полное звено: сигнал входит в проект, только если связан хотя бы с одним
    участником и не противоречит НИ ОДНОМУ. Заслон против цепного слипания."""
    proekty = []
    for s in sig:
        kuda, prich = None, ''
        for p in proekty:
            if any(protivorechie(s, m) for m in p['chleny']):
                continue
            luchshe = 0
            pr = ''
            for m in p['chleny']:
                sila, p_prich = svyaz(s, m)
                if sila > luchshe:
                    luchshe, pr = sila, p_prich
            if luchshe > 0:
                kuda, prich = p, pr
                break
        if kuda is None:
            proekty.append({'chleny': [s], 'prichiny': []})
        else:
            kuda['chleny'].append(s)
            kuda['prichiny'].append((s['_rid'], prich))
    return proekty


# ─────────────────────────────────────────────────────── оформление проекта
def oformit(p, imena):
    ch = p['chleny']
    inn = ch[0]['inn']
    gor = collections.Counter()
    reg = collections.Counter()
    rab = collections.Counter()
    for m in ch:
        gor.update(m['goroda'])
        reg.update(m['regiony'])
        rab.update(m['raboty'])
    yak = collections.Counter()
    for m in ch:
        yak.update(m['yak'])
    mesto = ' | '.join(g for g, _ in gor.most_common(3))
    region = ' | '.join(r for r, _ in reg.most_common(2))
    rabota = ' | '.join(r for r, _ in rab.most_common(2))
    obshch = [o for o, c in yak.most_common() if c >= max(2, len(ch) // 2)][:4]
    obekt = ' '.join(obshch)
    kl, sostav = L.klyuch_proekta(inn, mesto or region, obekt, rabota)

    daty = [m['data'] for m in ch if m['data']]
    gody = sorted({g for m in ch for g in m['god_iz_teksta']})
    ist = []
    for m in ch:
        if m['source'] and m['source'] not in ist:
            ist.append(m['source'])
    summy = [m['summa'] for m in ch if m['summa']]
    # стадия: по самому позднему доказательству, если даты есть; иначе максимальная
    if daty:
        pozdn = max(ch, key=lambda m: m['data'] or daty[0])
        stad_kod, stad = pozdn['stadiya_kod'], pozdn['stadiya']
    else:
        pozdn = max(ch, key=lambda m: m['stadiya_kod'])
        stad_kod, stad = pozdn['stadiya_kod'], pozdn['stadiya']
    ulik = [{'istochnik': m['source'], 'ssylka': m['url'],
             'citata': (m['what'] or '')[:400], 'data': str(m['data']) if m['data'] else '',
             'data_vzyatiya': m['updated_at'], 'event_type': m['event_type'],
             'summa_text': m['sum_text'], 'hotness': m['hotness'],
             'stadiya': m['stadiya'], 'inn_conf': m['inn_conf'], 'signal_rowid': m['_rid']}
            for m in ch]
    return {
        'proekt_id': kl,
        'klyuch_sostav': sostav,
        'inn_zakazchik': inn,
        'zakazchik': imena.get(inn, {}).get('name', ''),
        'zakazchik_iz': imena.get(inn, {}).get('otkuda', ''),
        'region': region,
        'region_iz': 'текст сигнала' if region else (
            'регистрация по ИНН' if imena.get(inn, {}).get('region') else ''),
        'region_po_inn': imena.get(inn, {}).get('region', ''),
        'mesto': mesto,
        'adres': imena.get(inn, {}).get('adres', ''),
        'obekt': obekt,
        'tip_rabot': rabota,
        'zontik': 1 if ch[0]['zontik'] else 0,
        'stadiya': stad,
        'stadiya_kod': stad_kod,
        'stadiya_rannyaya': min(m['stadiya_ran'] for m in ch),
        'stadiya_data': str(max(daty)) if daty else '',
        'stadiya_iz': pozdn['source'] + ' ' + (pozdn['url'] or '')[:120],
        'data_pervaya': str(min(daty)) if daty else '',
        'data_poslednyaya': str(max(daty)) if daty else '',
        'gody_iz_teksta': ','.join(str(g) for g in gody),
        'data_vzyatiya': max(m['updated_at'] for m in ch),
        'summa_rub': max(summy) if summy else '',
        'summa_text': ' | '.join(sorted({m['sum_text'] for m in ch if m['sum_text']})),
        'hotness_max': max([int(m['hotness']) for m in ch if str(m['hotness']).isdigit()]
                           or [0]),
        'dokazatelstv': len(ch),
        'istochnikov': len(ist),
        'istochniki': ' | '.join(ist),
        'podtverzhden': 1 if len(ist) >= 2 else 0,
        'event_types': ' | '.join(sorted({m['event_type'] for m in ch if m['event_type']})),
        'sklejka_prichiny': ' ;; '.join('%s: %s' % (a, b) for a, b in p['prichiny'])[:900],
        'dokazatelstva': ulik,
    }


# ─────────────────────────────────────────────────────────────────── main
def main(argv):
    syrye = chitat(argv)
    sig = [L.razobrat_signal(r) for r in syrye]
    df, zagl, stroch = statistika(sig)
    for s in sig:
        s['yak'] = yakorya(s, df, zagl, stroch)
        s['df'] = df
        s['zontik'] = (len(s['goroda']) + len(s['regiony'])) >= L.ZONTIK_MEST

    # гашение якорей без различающей силы внутри ИНН (собственное имя компании)
    po_inn = collections.defaultdict(list)
    for s in sig:
        po_inn[s['inn']].append(s)
    pogasheno = collections.Counter()
    for inn, gr in po_inn.items():
        if len(gr) < 4:
            continue
        c = collections.Counter()
        for s in gr:
            c.update(s['yak'])
        mert = {o for o, n in c.items() if n >= L.DOLYA_V_INN * len(gr)}
        for s in gr:
            s['yak'] -= mert
        for o in mert:
            pogasheno[o] += 1

    proekty = []
    for inn in sorted(po_inn):
        gr = sorted(po_inn[inn], key=lambda s: (-len(s['yak']), s['_rid']))
        proekty.extend(sobrat_proekty(gr))

    imena = imena_kompaniy({p['chleny'][0]['inn'] for p in proekty}, argv)
    gotovo = [oformit(p, imena) for p in proekty]
    gotovo.sort(key=lambda o: (-o['istochnikov'], -o['dokazatelstv'], o['inn_zakazchik']))
    return sig, gotovo, df, pogasheno


def imena_kompaniy(inny, argv):
    """Название/регион/адрес заказчика из базы. Имена колонок НЕ угадываются:
    таблицы осматриваются, найденные колонки печатаются."""
    if '--lokalno' in argv:
        return {}
    import sqlite3
    con = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    out = {}
    for tabl in ('companies', 'requisites', 'base_ref'):
        try:
            kol = [r[1] for r in con.execute('pragma table_info(%s)' % tabl)]
        except sqlite3.Error:
            continue
        print('  таблица %s колонки: %s' % (tabl, ','.join(kol)))
        if 'inn' not in kol:
            continue
        k_name = [c for c in kol if c.lower() in
                  ('name', 'company', 'title', 'short_name', 'name_short', 'org',
                   'company_name', 'nazvanie', 'full_name')]
        k_reg = [c for c in kol if 'region' in c.lower() or c.lower() in ('subject',)]
        k_adr = [c for c in kol if 'addr' in c.lower() or 'adres' in c.lower()]
        if not (k_name or k_reg or k_adr):
            continue
        sel = ['inn'] + k_name[:1] + k_reg[:1] + k_adr[:1]
        try:
            rows = con.execute('select %s from %s' % (','.join(sel), tabl)).fetchall()
        except sqlite3.Error as e:  # noqa: BLE001
            print('  %s: не прочиталась (%s)' % (tabl, str(e)[:60]))
            continue
        vzyato = 0
        for r in rows:
            i = (r['inn'] or '').strip()
            if not i or i not in inny:
                continue
            d = out.setdefault(i, {'name': '', 'region': '', 'adres': '', 'otkuda': ''})
            if k_name and not d['name'] and r[k_name[0]]:
                d['name'] = str(r[k_name[0]])[:160]
                d['otkuda'] = tabl + '.' + k_name[0]
                vzyato += 1
            if k_reg and not d['region'] and r[k_reg[0]]:
                d['region'] = str(r[k_reg[0]])[:80]
            if k_adr and not d['adres'] and r[k_adr[0]]:
                d['adres'] = str(r[k_adr[0]])[:200]
        print('  %s: имён взято %d' % (tabl, vzyato))
    return out


if __name__ == '__main__':
    A = sys.argv[1:]
    SIG, PROEKTY, DF, POG = main(A)
    n_p = len(PROEKTY)
    podt = sum(1 for p in PROEKTY if p['podtverzhden'])
    odin = sum(1 for p in PROEKTY if p['dokazatelstv'] == 1)
    mnogo = sum(1 for p in PROEKTY if p['dokazatelstv'] > 1)
    razm = collections.Counter(p['dokazatelstv'] for p in PROEKTY)

    if '--pisat' in A:
        VY = r'C:\sender\_ops\3s_proekty.jsonl'
        with io.open(VY, 'w', encoding='utf-8') as f:
            for p in PROEKTY:
                f.write(json.dumps(p, ensure_ascii=False) + '\n')
        import csv
        VC = r'C:\sender\_ops\3s_proekty.csv'
        pol = [k for k in PROEKTY[0] if k != 'dokazatelstva']
        with io.open(VC, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.writer(f, delimiter=';')
            w.writerow(pol + ['dokazatelstva_json'])
            for p in PROEKTY:
                w.writerow([p[k] for k in pol]
                           + [json.dumps(p['dokazatelstva'], ensure_ascii=False)])
        print('записано: %s и %s' % (VY, VC))
        try:
            import urllib.request
            for f_ in (VY, VC):
                op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                rq = urllib.request.Request(
                    '%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                               os.path.basename(f_)),
                    data=io.open(f_, 'rb').read(), method='PUT',
                    headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
                print('дроп %s: %s' % (os.path.basename(f_),
                                       op.open(rq, timeout=300).read()
                                       .decode('utf-8', 'replace')[:90]))
        except Exception as e:  # noqa: BLE001
            print('на дроп не выложено: %s' % str(e)[:120])

    print('\n########## ЧИСЛА СБОРКИ')
    print('  сигналов на входе             %5d' % len(SIG))
    print('  разных ИНН                    %5d' % len({s['inn'] for s in SIG}))
    print('  ПРОЕКТОВ собрано              %5d' % n_p)
    print('  подтверждены 2+ источниками   %5d' % podt)
    print('  одиночных (1 доказательство)  %5d' % odin)
    print('  с 2+ доказательствами         %5d' % mnogo)
    print('  размеры проектов: %s' % dict(sorted(razm.items())[:12]))
    print('  самый большой проект          %5d доказательств'
          % max(p['dokazatelstv'] for p in PROEKTY))
