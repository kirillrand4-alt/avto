# -*- coding: utf-8 -*-
"""Разведка (ТОЛЬКО отчёт): что уже покрыто по двум целевым спискам.

База продажников: C:\\sender\\_ops\\sales_base.json (словарь лист -> [{inn,name,phones,emails}])
Ядро центробежных: C:\\seostat\\drop\\drop-storage\\centrifugal-core-inns.txt

Ничего не пишет и не обогащает: читает исходники, потоки резюма и enrich.db,
печатает JSON со сводкой. Нужен, чтобы понять размер остатка перед прогоном.
"""
import glob
import json
import os
import re
import sqlite3

OPS = r'C:\sender\_ops'
SRV = r'C:\sender\server'
DB = r'C:\sender\enrich.db'
CORE_TXT = r'C:\seostat\drop\drop-storage\centrifugal-core-inns.txt'

INN_RE = re.compile(r'\b(\d{10}|\d{12})\b')


def load_sales():
    """Плоский список записей базы продажников + карта ИНН -> запись."""
    p = os.path.join(OPS, 'sales_base.json')
    if not os.path.exists(p):
        return [], {'error': 'sales_base.json не найден'}
    d = json.load(open(p, encoding='utf-8'))
    rows, sheets = [], {}
    if isinstance(d, dict):
        for sheet, items in d.items():
            if not isinstance(items, list):
                continue
            sheets[sheet] = len(items)
            for it in items:
                if isinstance(it, dict):
                    r = dict(it)
                    r['_sheet'] = sheet
                    rows.append(r)
    elif isinstance(d, list):
        rows = [x for x in d if isinstance(x, dict)]
        sheets['(список)'] = len(rows)
    return rows, {'листы': sheets}


def load_core():
    if not os.path.exists(CORE_TXT):
        return []
    out = []
    for ln in open(CORE_TXT, encoding='utf-8', errors='replace'):
        m = INN_RE.search(ln)
        if m:
            out.append(m.group(1))
    return out


def stream_done(pattern):
    """Повторяет логику resume из enrich_contacts.main(): что считается сделанным."""
    done, attempts = set(), {}
    base = os.path.join(SRV, pattern)
    files = set(glob.glob(base)) | set(glob.glob(base.rsplit('.', 1)[0] + '*.jsonl'))
    for fp in sorted(files):
        try:
            for ln in open(fp, encoding='utf-8', errors='replace'):
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
        except Exception:  # noqa: BLE001
            continue
    return done, attempts, sorted(os.path.basename(f) for f in files)


def db_stats(inns):
    """Покрытие набора ИНН по таблицам enrich.db."""
    out = {'db_exists': os.path.exists(DB)}
    if not out['db_exists']:
        return out
    cx = sqlite3.connect(f'file:{DB}?mode=ro', uri=True, timeout=30)
    cx.row_factory = sqlite3.Row
    tabs = [r[0] for r in cx.execute(
        "select name from sqlite_master where type='table'").fetchall()]
    out['таблицы'] = tabs
    tmp = 'inn_probe_tmp'
    cx.execute(f'create temp table {tmp}(inn text primary key)')
    cx.executemany(f'insert or ignore into {tmp} values(?)', [(i,) for i in inns])

    def one(sql):
        try:
            return cx.execute(sql).fetchone()[0]
        except Exception as e:  # noqa: BLE001
            return f'err: {str(e)[:70]}'

    out['в_companies'] = one(
        f'select count(*) from companies c join {tmp} t on t.inn=c.inn')
    out['с_сайтом'] = one(
        f"select count(*) from companies c join {tmp} t on t.inn=c.inn "
        f"where coalesce(c.site,'')<>''")
    out['ИНН_с_email'] = one(
        f'select count(distinct e.inn) from emails e join {tmp} t on t.inn=e.inn')
    out['email_всего'] = one(
        f'select count(*) from emails e join {tmp} t on t.inn=e.inn')
    if 'phone_contacts' in tabs:
        out['ИНН_с_телефоном'] = one(
            f'select count(distinct p.inn) from phone_contacts p join {tmp} t on t.inn=p.inn')
        out['телефонов_всего'] = one(
            f'select count(*) from phone_contacts p join {tmp} t on t.inn=p.inn')
        out['телефонов_с_ссылкой'] = one(
            f"select count(*) from phone_contacts p join {tmp} t on t.inn=p.inn "
            f"where coalesce(p.source_url,'')<>''")
        try:
            out['телефоны_по_источникам'] = {
                r[0]: r[1] for r in cx.execute(
                    f'select coalesce(p.source,\'?\'), count(*) from phone_contacts p '
                    f'join {tmp} t on t.inn=p.inn group by 1 order by 2 desc').fetchall()}
        except Exception:  # noqa: BLE001
            pass
    try:
        out['стадии'] = {r[0]: r[1] for r in cx.execute(
            f'select s.stage, count(distinct s.inn) from stage_log s '
            f'join {tmp} t on t.inn=s.inn group by 1 order by 2 desc').fetchall()}
    except Exception:  # noqa: BLE001
        pass
    cx.close()
    return out


def main():
    sales_rows, sales_meta = load_sales()
    sales_inns, sales_named = [], 0
    seen = set()
    for r in sales_rows:
        i = str(r.get('inn') or '').strip()
        m = INN_RE.search(i) if i else None
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        sales_inns.append(m.group(1))
        if (r.get('name') or '').strip():
            sales_named += 1

    core_inns_all = load_core()
    core_inns = sorted(set(core_inns_all))

    core_json = os.path.join(SRV, 'core396.json')
    core_named = 0
    if os.path.exists(core_json):
        try:
            cj = json.load(open(core_json, encoding='utf-8'))
            have = {str(c.get('inn')): (c.get('name') or '') for c in cj}
            core_named = sum(1 for i in core_inns if have.get(i))
        except Exception:  # noqa: BLE001
            pass

    res = {'op': '_recon_bases'}
    res['продажники'] = {
        'строк_в_файле': len(sales_rows),
        'уникальных_ИНН': len(sales_inns),
        'с_названием': sales_named,
        **sales_meta,
    }
    res['ядро'] = {
        'строк_с_ИНН': len(core_inns_all),
        'уникальных_ИНН': len(core_inns),
        'из_них_с_именем_в_core396': core_named,
    }
    res['пересечение_списков'] = len(set(sales_inns) & set(core_inns))

    for label, inns, stream in (('продажники', sales_inns, 'enrich_sales*.jsonl'),
                                ('ядро', core_inns, 'enrich_core2.jsonl')):
        done, att, files = stream_done(stream)
        mine_done = sorted(set(inns) & done)
        exhausted = {i for i, c in att.items()
                     if c >= 3 and i not in done and i in set(inns)}
        res[label]['поток'] = {
            'файлы': files,
            'done_в_потоке_всего': len(done),
            'done_из_нашего_списка': len(mine_done),
            'исчерпано_попыток': len(exhausted),
            'ОСТАЛОСЬ_К_ПРОГОНУ': len(set(inns) - done - exhausted),
        }
        res[label]['бд'] = db_stats(inns)

    print(json.dumps(res, ensure_ascii=False))


if __name__ == '__main__':
    main()
