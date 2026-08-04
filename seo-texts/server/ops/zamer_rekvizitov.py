# -*- coding: utf-8 -*-
"""Что пусто в реквизитах карточек и ГДЕ это лежит в наших источниках."""
import os, sqlite3, sys, json
ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
кол = [c[1] for c in цб.execute('PRAGMA table_info(company)')]
всего = цб.execute('SELECT COUNT(*) FROM company').fetchone()[0]
print(f'компаний в панели: {всего}')
поля = ['region','address','director','status','site','okved_main','okved_all',
        'revenue','revenue_num','staff','profit','ogrn','kpp','equipment']
print('ЗАПОЛНЕНО в company:')
for п in поля:
    if п not in кол:
        print(f'  {п:12} — КОЛОНКИ НЕТ'); continue
    n = цб.execute(f"SELECT COUNT(*) FROM company WHERE COALESCE({п},'') NOT IN ('','0','—')").fetchone()[0]
    print(f'  {п:12} {n:5} из {всего}  ({100*n//max(всего,1)}%)')
цб.close()

# что есть в enrich.db — там кэш checko/dadata
sys.path.insert(0, r'C:\sender\server')
try:
    import enrich_db as EDB
    db = EDB.EnrichDB()
    т = [r[0] for r in db.cx.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    print('\nтаблицы enrich.db:', ', '.join(т))
    for имя in т:
        try:
            c = db.cx.execute(f'SELECT COUNT(*) FROM {имя}').fetchone()[0]
            колн = [x[1] for x in db.cx.execute(f'PRAGMA table_info({имя})')]
            интерес = [k for k in colnames if k in колн] if False else [
                k for k in ('inn','okved','okved_main','okved_all','address','region',
                            'director','revenue','staff','site','status','name')
                if k in колн]
            if интерес and c:
                print(f'  {имя:22} строк {c:6} интересные колонки: {интерес}')
        except Exception:
            pass
except Exception as e:
    print('enrich.db не прочитан:', str(e)[:120])
