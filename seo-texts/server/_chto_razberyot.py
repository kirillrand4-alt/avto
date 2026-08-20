# -*- coding: utf-8 -*-
r"""Что провайдер будет разбирать, когда снимем холд: очередь в числах."""
import gzip, json, os, sqlite3

KESH = r'C:\seostat\drop\pagecache'
BD = r'C:\sender\enrich.db'
итог = {}
кэш = set()
if os.path.isdir(KESH):
    for n in os.listdir(KESH):
        if n.endswith('.json.gz'):
            и = n.split('.')[0]
            if и.isdigit():
                кэш.add(и)
итог['страниц_снято_компаний'] = len(кэш)

c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
c.row_factory = sqlite3.Row
паспорта = {str(r[0]) for r in c.execute('select distinct inn from site_facts')}
итог['паспортов_есть'] = len(паспорта)
итог['БЕЗ_ПАСПОРТА_из_снятых'] = len(кэш - паспорта)

# роли: почты с должностью/ФИО
итог['почт_всего'] = c.execute('select count(*) from emails').fetchone()[0]
кол = [r[1] for r in c.execute('pragma table_info(emails)')]
итог['столбцы_emails'] = кол
if 'role' in кол:
    итог['почт_с_ролью'] = c.execute(
        "select count(*) from emails where coalesce(role,'')<>''").fetchone()[0]
if 'person' in кол:
    итог['почт_с_фио'] = c.execute(
        "select count(*) from emails where coalesce(person,'')<>''").fetchone()[0]
итог['людей_в_imena'] = c.execute('select count(*) from imena').fetchone()[0]
# сколько компаний со страницами вообще не имеют ни одной почты
с_почтой = {str(r[0]) for r in c.execute("select distinct inn from emails")}
итог['снятых_БЕЗ_единой_почты'] = len(кэш - с_почтой)
# паспорта: качество
# json_extract спотыкается на битой строке — считаем в Python
ув = {}
for (js,) in c.execute("select facts_json from site_facts "
                       "where coalesce(facts_json,'')<>''"):
    try:
        ув.setdefault(json.loads(js).get('уверенность') or '?', 0)
        ув[json.loads(js).get('уверенность') or '?'] += 1
    except Exception:
        ув['битый JSON'] = ув.get('битый JSON', 0) + 1
итог['паспорта_по_уверенности'] = ув
c.close()
print(json.dumps(итог, ensure_ascii=False, indent=1))
