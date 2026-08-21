# -*- coding: utf-8 -*-
r"""Что вообще есть по компании: колонки таблиц и живой пример по «Кейтерингу»."""
import json
import sqlite3

ИНН = '7719414324'
e = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
e.row_factory = sqlite3.Row
d = {}
for т in ('companies', 'people', 'qc_site', 'base_ref', 'emails'):
    try:
        d['колонки_' + т] = [x[1] for x in e.execute('PRAGMA table_info(%s)' % т)]
    except Exception as ex:  # noqa: BLE001
        d['колонки_' + т] = str(ex)[:60]
ряд = e.execute('select * from companies where inn=?', (ИНН,)).fetchone()
d['компания'] = {k: (str(v)[:80] if v is not None else None)
                 for k, v in dict(ряд).items() if v not in (None, '', 0)} if ряд else {}
qc = e.execute('select url, phones, n_phones from qc_site where inn=?',
               (ИНН,)).fetchone()
d['qc_site'] = dict(qc) if qc else {}
br = e.execute('select * from base_ref where inn=?', (ИНН,)).fetchone()
d['base_ref'] = {k: str(v)[:70] for k, v in dict(br).items()} if br else {}
sf = e.execute("select coalesce(facts_json,'') f, coalesce(site,'') s, "
               "coalesce(sources_json,'') src from site_facts where inn=?",
               (ИНН,)).fetchone()
if sf:
    try:
        ф = json.loads(sf['f'] or '{}')
    except Exception:  # noqa: BLE001
        ф = {}
    d['паспорт_ключи'] = {k: (len(v) if isinstance(v, list) else str(v)[:60])
                          for k, v in ф.items()}
    d['паспорт_продукция'] = (ф.get('продукция') or [])[:6]
    d['паспорт_источники'] = (ф.get('источники') or [])[:4]
d['людей'] = [dict(r) for r in e.execute(
    'select * from people where inn=? limit 4', (ИНН,))]
d['почты'] = [{k: str(v)[:50] for k, v in dict(r).items()} for r in e.execute(
    'select * from emails where inn=? limit 4', (ИНН,))]
e.close()
print(json.dumps(d, ensure_ascii=False, indent=1)[:5000])
