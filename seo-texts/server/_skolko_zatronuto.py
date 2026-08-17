# -*- coding: utf-8 -*-
"""Сколько компаний пострадало от coalesce: site='' (не NULL) при живом cand_site."""
import json
import sqlite3
import sys

c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
итог = {
 'site_пустая_строка_и_есть_кандидат': c.execute(
     "select count(*) from companies where coalesce(site,'')='' and site is not null "
     "and coalesce(cand_site,'')<>''").fetchone()[0],
 'site_NULL_и_есть_кандидат': c.execute(
     "select count(*) from companies where site is null and coalesce(cand_site,'')<>''"
 ).fetchone()[0],
 'всего_с_кандидатом_без_сайта': c.execute(
     "select count(*) from companies where coalesce(site,'')='' "
     "and coalesce(cand_site,'')<>''").fetchone()[0],
}
c.close()
sys.stdout.reconfigure(encoding='utf-8')
print(json.dumps(итог, ensure_ascii=False, indent=1))
