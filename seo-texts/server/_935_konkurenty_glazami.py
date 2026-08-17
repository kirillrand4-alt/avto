# -*- coding: utf-8 -*-
"""13 конкурентов в группе: что про них знает карточка — судить глазами.

Флаг is_competitor ставила модель обхода, а её просили «при сомнении false»,
но ошибки бывают в обе стороны. Прежде чем стопить — смотрим род занятий.
"""
import json
import sqlite3
import sys

ENRICH = r'C:\sender\enrich.db'
SENDER = r'C:\sender\sender.db'


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    s = sqlite3.connect('file:%s?mode=ro' % SENDER.replace('\\', '/'), uri=True)
    в_группе = {''.join(c for c in str(r[0] or '') if c.isdigit())
                for r in s.execute("select inn from recipients "
                                   "where extra_json like '%Партия 935%'")}
    стоп = {''.join(c for c in str(r[0]) if c.isdigit())
            for r in s.execute("select value from suppression where scope='inn'")}
    s.close()
    e = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
    e.row_factory = sqlite3.Row
    из = []
    for r in e.execute("select inn, coalesce(name,'') name, is_competitor k, "
                       "coalesce(activity,'') act, "
                       "coalesce(nullif(site,''),nullif(cand_site,''),'') site, "
                       "coalesce(okved,'') okved from companies"):
        инн = str(r['inn'])
        if инн not in в_группе:
            continue
        if str(r['k'] or '').strip().lower() not in ('1', 'true', 'да', 'yes'):
            continue
        из.append({'инн': инн, 'имя': r['name'][:45], 'сайт': r['site'],
                   'оквэд': r['okved'][:55], 'занятие': r['act'][:160],
                   'в_стопе': инн in стоп})
    e.close()
    print(json.dumps(из, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
