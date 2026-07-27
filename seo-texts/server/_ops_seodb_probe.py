# -*- coding: utf-8 -*-
"""Что seo.db добавляет по нашим 555+396 ИНН сверх obzvon-index.db (только чтение)."""
import json
import re
import sqlite3

SEO = r'C:\seostat\data\seo.db'
OBZ = r'C:\sender\obzvon-index.db'
SALES = r'C:\sender\_ops\sales_base.json'
CORE = r'C:\seostat\drop\drop-storage\centrifugal-core-inns.txt'
INN_RE = re.compile(r'\b(\d{10}|\d{12})\b')


def load():
    sales, core = [], []
    d = json.load(open(SALES, encoding='utf-8'))
    seen = set()
    for v in d.values():
        for it in (v or []):
            m = INN_RE.search(str(it.get('inn') or ''))
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                sales.append(m.group(1))
    s2 = set()
    for ln in open(CORE, encoding='utf-8', errors='replace'):
        m = INN_RE.search(ln)
        if m and m.group(1) not in s2:
            s2.add(m.group(1))
            core.append(m.group(1))
    return sales, core


def main():
    sales, core = load()
    allinn = sorted(set(sales) | set(core))
    out = {'ИНН_всего': len(allinn), 'продажники': len(sales), 'ядро': len(core)}

    cx = sqlite3.connect(f'file:{SEO}?mode=ro', uri=True, timeout=60)
    cx.execute('create temp table t(inn text primary key)')
    cx.executemany('insert or ignore into t values(?)', [(i,) for i in allinn])

    out['в_call_company'] = cx.execute(
        'select count(*) from call_company c join t on t.inn=c.inn').fetchone()[0]
    out['по_базам'] = dict(cx.execute(
        'select c.base, count(*) from call_company c join t on t.inn=c.inn '
        'group by 1').fetchall())
    cols = [r[1] for r in cx.execute('PRAGMA table_info(call_company)')]
    out['колонки_call_company'] = cols
    # чем call_company богаче obzvon-index: какие поля непусты
    rich = {}
    for col in cols:
        if col in ('id', 'base', 'inn'):
            continue
        try:
            n = cx.execute(
                f"select count(*) from call_company c join t on t.inn=c.inn "
                f"where coalesce(c.{col},'')<>''").fetchone()[0]
            if n:
                rich[col] = n
        except Exception:  # noqa: BLE001
            pass
    out['непустых_полей_по_нашим'] = rich
    cx.close()

    ox = sqlite3.connect(f'file:{OBZ}?mode=ro', uri=True, timeout=60)
    ox.execute('create temp table t(inn text primary key)')
    ox.executemany('insert or ignore into t values(?)', [(i,) for i in allinn])
    out['в_obzvon_index'] = ox.execute(
        'select count(*) from obzvon o join t on t.inn=o.inn').fetchone()[0]
    ox.close()
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
