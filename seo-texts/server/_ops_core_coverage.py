# -*- coding: utf-8 -*-
"""Покрытие ядра центробежных: сколько из 396 реально обработано."""
import json
import re
import sqlite3

CORE = r'C:\seostat\drop\drop-storage\centrifugal-core-inns.txt'
STREAM = r'C:\sender\server\enrich_core2.jsonl'
DB = r'C:\sender\enrich.db'
INN_RE = re.compile(r'\b(\d{10}|\d{12})\b')


def main():
    core = []
    seen = set()
    for ln in open(CORE, encoding='utf-8', errors='replace'):
        m = INN_RE.search(ln)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            core.append(m.group(1))

    done, attempts = set(), {}
    for ln in open(STREAM, encoding='utf-8', errors='replace'):
        try:
            j = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        inn = str(j.get('inn') or '')
        if not inn:
            continue
        attempts[inn] = attempts.get(inn, 0) + 1
        if j.get('extract') == 'regex-provider-fail':
            done.discard(inn)
            continue
        if (j.get('emails') or j.get('best_for_outreach')
                or j.get('verified') or j.get('method') == 'ok'):
            done.add(inn)

    cs = set(core)
    exhausted = {i for i, c in attempts.items() if c >= 3 and i not in done and i in cs}
    out = {
        'ИНН_в_ядре': len(core),
        'обработано': len(cs & done),
        'исчерпало_попытки': len(exhausted),
        'осталось': len(cs - done - exhausted),
    }

    cx = sqlite3.connect(f'file:{DB}?mode=ro', uri=True, timeout=60)
    cx.execute('create temp table t(inn text primary key)')
    cx.executemany('insert or ignore into t values(?)', [(i,) for i in core])
    out['в_БД'] = {
        'компаний': cx.execute(
            'select count(*) from companies c join t on t.inn=c.inn').fetchone()[0],
        'с_сайтом': cx.execute(
            "select count(*) from companies c join t on t.inn=c.inn "
            "where coalesce(c.site,'')<>''").fetchone()[0],
        'ИНН_с_телефоном': cx.execute(
            'select count(distinct p.inn) from phone_contacts p '
            'join t on t.inn=p.inn').fetchone()[0],
        'ИНН_с_email': cx.execute(
            'select count(distinct e.inn) from emails e join t on t.inn=e.inn'
        ).fetchone()[0],
        'телефонов_ЕИС': cx.execute(
            "select count(*) from phone_contacts p join t on t.inn=p.inn "
            "where p.source='zakupki:eis'").fetchone()[0],
    }
    out['стадии'] = {r[0]: r[1] for r in cx.execute(
        'select s.stage, count(distinct s.inn) from stage_log s join t on t.inn=s.inn '
        'group by 1 order by 2 desc limit 8')}
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
