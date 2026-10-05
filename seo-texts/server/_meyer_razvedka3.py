# -*- coding: utf-8 -*-
"""Разведка значений перед выгрузкой мейеровской базы: роли, источники, ссылки, форматы."""
import json
import sqlite3

o = {}
c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=60)
c.execute(r"attach database 'file:C:\sender\obzvon-index.db?mode=ro' as obz")


def топ(sql, n=25):
    return [list(r) for r in c.execute(sql + ' limit %d' % n)]


o['emails_role'] = топ("select role, count(*) n from emails group by role order by n desc", 30)
o['emails_source'] = топ("select source, count(*) n from emails group by source order by n desc", 20)
o['emails_verdict'] = топ("select probe_verdict, count(*) n from emails group by probe_verdict order by n desc", 15)
o['emails_url_пример'] = топ("select source, source_url from emails where coalesce(source_url,'')<>'' "
                             "group by source", 15)
o['emails_с_url'] = c.execute("select sum(coalesce(source_url,'')<>''), count(*) from emails").fetchone()
o['phones_role'] = топ("select role, count(*) n from phone_contacts group by role order by n desc", 25)
o['phones_source'] = топ("select source, count(*) n from phone_contacts group by source order by n desc", 20)
o['phones_с_url'] = c.execute("select sum(coalesce(source_url,'')<>''), count(*) from phone_contacts").fetchone()
o['people_post'] = топ("select post, count(*) n from people group by post order by n desc", 25)
o['people_source'] = топ("select source, count(*) n, max(source_url) from people group by source order by n desc", 15)
o['imena_post'] = топ("select post, count(*) n from imena group by post order by n desc", 20)
o['imena_istochnik'] = топ("select substr(istochnik,1,90), count(*) n from imena group by istochnik order by n desc", 10)
o['site_facts_пример'] = [(r[0] or '')[:600] for r in c.execute(
    "select facts_json from site_facts where length(facts_json)>200 limit 2")]
o['companies_выручка'] = топ("select revenue_rub, revenue_year, typeof(revenue_rub) from companies "
                             "where coalesce(revenue_rub,0)<>0", 4)
o['obzvon_пример'] = топ("select base_label, division, phones_base, emails_base, phones_site, emails_site, "
                         "sites, revenue, god_otch, revenue_rub, typeof(revenue_rub), director, region, "
                         "substr(address,1,60) from obz.obzvon where coalesce(phones_base,'')<>''", 3)
o['obzvon_labels'] = топ("select base_label, division, count(*) n from obz.obzvon group by 1,2 order by n desc", 15)
o['obzvon_cols'] = [r[1] for r in c.execute('pragma obz.table_info(obzvon)')]
o['obzvon_покрытие'] = c.execute(
    "select sum(coalesce(phones_base,'')<>''), sum(coalesce(emails_base,'')<>''), "
    "sum(coalesce(phones_site,'')<>''), sum(coalesce(emails_site,'')<>''), count(*) from obz.obzvon").fetchone()
c.close()
print('===ИТОГ===')
ключи=['emails_role','emails_source','emails_verdict','emails_url_пример','emails_с_url','phones_role','phones_source','phones_с_url','people_post']
for к in ключи:
    print(к, json.dumps(o[к], ensure_ascii=False, default=str)[:1800])
