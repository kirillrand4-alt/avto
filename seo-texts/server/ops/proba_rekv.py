import os, sqlite3, sys, json
ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True)
кол = [c[1] for c in цб.execute('PRAGMA table_info(company)')]
print('КОЛОНКИ company в живой базе:', кол)
r = цб.execute("SELECT * FROM company WHERE inn='2635040105'").fetchone()
if r: print('строка Ставрополькрайводоканал:', dict(zip(кол, r)))
цб.close()
sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB
db = EDB.EnrichDB()
for т in ('companies','requisites','base_ref'):
    к = [x[1] for x in db.cx.execute(f'PRAGMA table_info({т})')]
    row = db.cx.execute(f"SELECT * FROM {т} WHERE inn='2635040105'").fetchone()
    print(f'\n--- {т} колонки: {к}')
    if row:
        d = dict(zip(к, row))
        print('   ', {k: (str(v)[:90] if v not in (None,'') else '') for k, v in d.items() if v not in (None,'')})
    else:
        print('    нет строки по этому ИНН')
# охват по нашим 1573
инны = {str(x[0]) for x in sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True).execute('SELECT inn FROM company')}
for т, поля in (('companies', 'okved,okved_all,region,director,site'),
                ('requisites','okved_main,okved_all,address,director,status'),
                ('base_ref','revenue,site')):
    к = [x[1] for x in db.cx.execute(f'PRAGMA table_info({т})')]
    есть = {str(x[0]) for x in db.cx.execute(f'SELECT inn FROM {т}')}
    print(f'{т}: покрывает {len(инны & есть)} из {len(инны)} наших ИНН')
