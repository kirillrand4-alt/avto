# -*- coding: utf-8 -*-
"""Что реально собрано по базе продажников: сайты, ЕИС, checko, hh, стадии."""
import json
import os
import re
import sqlite3

DB = r'C:\sender\enrich.db'
SALES = r'C:\sender\_ops\sales_base.json'
STREAM = r'C:\sender\server\enrich_sales.jsonl'
INN_RE = re.compile(r'\b(\d{10}|\d{12})\b')


def sales_inns():
    d = json.load(open(SALES, encoding='utf-8'))
    out = []
    seen = set()
    items = []
    for v in d.values():
        items.extend(v or [])
    for r in items:
        m = INN_RE.search(str(r.get('inn') or ''))
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(m.group(1))
    return out


def main():
    inns = sales_inns()
    cx = sqlite3.connect(f'file:{DB}?mode=ro', uri=True, timeout=60)
    cx.execute('create temp table t(inn text primary key)')
    cx.executemany('insert or ignore into t values(?)', [(i,) for i in inns])
    out = {'ИНН_в_базе': len(inns)}

    out['телефоны_по_источникам'] = {r[0] or '?': r[1] for r in cx.execute(
        'select p.source, count(*) from phone_contacts p join t on t.inn=p.inn '
        'group by 1 order by 2 desc')}
    out['email_по_источникам'] = {r[0] or '?': r[1] for r in cx.execute(
        'select e.source, count(*) from emails e join t on t.inn=e.inn '
        'group by 1 order by 2 desc')}
    out['стадии_пройдено_ИНН'] = {r[0]: r[1] for r in cx.execute(
        'select s.stage, count(distinct s.inn) from stage_log s join t on t.inn=s.inn '
        'group by 1 order by 2 desc')}
    out['компаний_с_сайтом'] = cx.execute(
        "select count(*) from companies c join t on t.inn=c.inn "
        "where coalesce(c.site,'')<>''").fetchone()[0]
    out['компаний_с_выручкой'] = cx.execute(
        "select count(*) from companies c join t on t.inn=c.inn "
        "where coalesce(c.revenue_rub,'')<>''").fetchone()[0]
    out['компаний_с_activity'] = cx.execute(
        "select count(*) from companies c join t on t.inn=c.inn "
        "where coalesce(c.activity,'')<>''").fetchone()[0]

    # новостные поводы
    out['новостные_поводы'] = {
        'ИНН_с_сигналами': cx.execute(
            'select count(distinct s.inn) from signals s join t on t.inn=s.inn'
        ).fetchone()[0],
        'сигналов_всего': cx.execute(
            'select count(*) from signals s join t on t.inn=s.inn').fetchone()[0],
        'по_источникам': {r[0] or '?': r[1] for r in cx.execute(
            'select s.source, count(*) from signals s join t on t.inn=s.inn '
            'group by 1 order by 2 desc limit 12')},
        'по_типам': {r[0] or '?': r[1] for r in cx.execute(
            'select s.event_type, count(*) from signals s join t on t.inn=s.inn '
            'group by 1 order by 2 desc limit 12')},
        'горячие': [{'инн': r[0], 'что': (r[1] or '')[:80], 'накал': r[2],
                     'ссылка': (r[3] or '')[:70]}
                    for r in cx.execute(
            'select s.inn, s.what, s.hotness, s.source_url from signals s '
            'join t on t.inn=s.inn order by coalesce(s.hotness,0) desc limit 6')],
    }

    # что дал ИМЕННО этот прогон — по потоку
    if os.path.exists(STREAM):
        zak = hh = opo = crawl = 0
        zak_cards = 0
        for ln in open(STREAM, encoding='utf-8', errors='replace'):
            try:
                j = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            z = j.get('zakupki')
            if isinstance(z, dict) and z.get('cards'):
                zak += 1
                zak_cards += len(z['cards'])
            if j.get('hh'):
                hh += 1
            if isinstance(j.get('opo'), dict) and j['opo'].get('opo'):
                opo += 1
            if (j.get('timings') or {}).get('crawl'):
                crawl += 1
        out['этот_прогон'] = {'краул_сайта': crawl, 'ЕИС_с_карточками': zak,
                              'карточек_закупок': zak_cards, 'hh_сигнал': hh,
                              'ОПО': opo}
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
