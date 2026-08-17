# -*- coding: utf-8 -*-
"""Чем в базе отличается почта, найденная НА САЙТЕ, от пришедшей из выгрузки."""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\sender\server')
import ploshchadki as PL  # noqa: E402

c = sqlite3.connect('file:%s?mode=ro' % r'C:/sender/enrich.db', uri=True)
c.row_factory = sqlite3.Row
итог = {}
итог['по_source'] = [dict(r) for r in c.execute(
    "select coalesce(source,'(пусто)') istochnik, count(*) adresov, "
    "count(distinct inn) kompaniy, sum(case when coalesce(source_url,'')<>'' then 1 else 0 end) so_ssylkoy "
    'from emails group by 1 order by adresov desc limit 14')]
итог['по_pometka'] = [dict(r) for r in c.execute(
    "select coalesce(pometka,'(пусто)') pometka, count(*) skolko from emails "
    'group by 1 order by skolko desc limit 10')]
итог['по_addr_class'] = [dict(r) for r in c.execute(
    "select coalesce(addr_class,'(пусто)') klass, count(*) skolko from emails "
    'group by 1 order by skolko desc limit 10')]
итог['с_ссылкой_на_страницу'] = c.execute(
    "select count(*) from emails where coalesce(source_url,'')<>''").fetchone()[0]
итог['компаний_с_ссылкой'] = c.execute(
    "select count(distinct inn) from emails where coalesce(source_url,'')<>''").fetchone()[0]
итог['примеры'] = [dict(r) for r in c.execute(
    "select inn, email, coalesce(source,'') source, substr(coalesce(source_url,''),1,60) url, "
    "coalesce(razdel,'') razdel, coalesce(pometka,'') pometka from emails "
    "where coalesce(source_url,'')<>'' limit 4")]
c.close()
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
