import os, sqlite3, re
ЦБ = r'C:\seostat\data\centrifugal.db'
наши = {str(r[0]) for r in sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True).execute('SELECT inn FROM company')}
print('наших ИНН:', len(наши))
for имя, путь, табл in (('obzvon-index', r'C:\sender\obzvon-index.db', 'obzvon'),
                        ('seo.db call_company', r'C:\seostat\data\seo.db', 'call_company')):
    if not os.path.exists(путь):
        print(f'{имя}: ФАЙЛА НЕТ ({путь})'); continue
    try:
        cx = sqlite3.connect(f'file:{путь}?mode=ro', uri=True, timeout=20)
        к = [c[1] for c in cx.execute(f'PRAGMA table_info({табл})')]
        n = cx.execute(f'SELECT COUNT(*) FROM {табл}').fetchone()[0]
        print(f'\n{имя}: строк {n}')
        print('  колонки:', к)
        поле_инн = 'inn' if 'inn' in к else к[0]
        есть = {str(r[0]) for r in cx.execute(f'SELECT {поле_инн} FROM {табл}')}
        print(f'  покрывает наших: {len(наши & есть)} из {len(наши)}')
        # пример по компании владельца
        r = cx.execute(f"SELECT * FROM {табл} WHERE {поле_инн}='2635040105'").fetchone()
        if r:
            d = {k: v for k, v in zip(к, r) if v not in (None, '')}
            print('  Ставрополькрайводоканал:', {k: str(v)[:70] for k, v in list(d.items())[:14]})
        cx.close()
    except Exception as e:
        print(f'{имя}: ошибка {str(e)[:100]}')
