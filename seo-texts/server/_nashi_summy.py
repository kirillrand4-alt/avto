# -*- coding: utf-8 -*-
"""Насколько у нас заполнено поле суммы в событиях."""
import json, re, sqlite3

c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=30)
o = {}
o['всего'] = c.execute('select count(*) from signals').fetchone()[0]
o['с_суммой'] = c.execute("select count(*) from signals where coalesce(sum,'')<>''").fetchone()[0]
o['с_суммой_свежие'] = c.execute(
    "select count(*) from signals where coalesce(sum,'')<>'' "
    "and substr(updated_at,1,10) >= '2026-09-16'").fetchone()[0]
o['свежих_всего'] = c.execute(
    "select count(*) from signals where substr(updated_at,1,10) >= '2026-09-16'").fetchone()[0]
o['примеры'] = c.execute(
    "select coalesce(cmp.name,s.inn), substr(s.what,1,55), s.sum "
    'from signals s left join companies cmp on cmp.inn=s.inn '
    "where coalesce(s.sum,'')<>'' order by s.rowid desc limit 8").fetchall()
# в тексте события сумма часто есть, даже если поле пустое
строки = c.execute("select what from signals where coalesce(sum,'')='' limit 2000").fetchall()
есть_в_тексте = sum(1 for (w,) in строки if re.search(r'\d[\d\s.,]*\s*(млн|млрд)', w or ''))
o['без_поля_но_сумма_в_тексте'] = '%d из %d проверенных' % (есть_в_тексте, len(строки))
c.close()
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1, default=str)[:4000])
