# -*- coding: utf-8 -*-
"""Заполненность реквизитов в пересобранном снимке + контрольная компания."""
import json
import sqlite3

CENTRO = r'C:\seostat\data\centrifugal.db'
COLS = ['ogrn', 'kpp', 'okpo', 'opf', 'opf_full', 'reg_date', 'status', 'address',
        'region', 'director', 'director_post', 'director_inn', 'founders',
        'capital', 'equity', 'okved_main', 'okved_all', 'okved_reason',
        'calc_comment', 'revenue', 'profit', 'staff', 'site', 'activity']
PROBE = '6320002223'


def main():
    cx = sqlite3.connect(f'file:{CENTRO}?mode=ro', uri=True, timeout=60)
    cx.row_factory = sqlite3.Row
    sel = ', '.join(f"sum(case when coalesce(trim({c}),'')<>'' then 1 else 0 end)"
                    for c in COLS)
    row = cx.execute(f'select count(*), {sel} from company').fetchone()
    out = {'строк': row[0], 'заполнено': {c: row[i] for i, c in enumerate(COLS, 1)}}
    out['статусы'] = [{'значение': r[0], 'строк': r[1]} for r in cx.execute(
        "select coalesce(status,'—'), count(*) from company group by 1 order by 2 desc")]
    r = cx.execute('select * from company where inn=? limit 1', (PROBE,)).fetchone()
    out['контрольная'] = {k: (str(r[k])[:120] if r[k] not in (None, '') else None)
                          for k in r.keys()} if r else 'нет'
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
