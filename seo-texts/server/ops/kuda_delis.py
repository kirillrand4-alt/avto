# -*- coding: utf-8 -*-
"""Пункт 11 владельца: куда делись компании из панели. Отчёт по скрытиям."""
import os, sqlite3, re
from collections import Counter
ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПР = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
кол = [c[1] for c in цб.execute('PRAGMA table_info(company)')]
база_к = 'base' if 'base' in кол else None
всего = цб.execute('SELECT COUNT(*) FROM company').fetchone()[0]
по_базам = Counter()
if база_к:
    for б, n in цб.execute(f'SELECT COALESCE({база_к},"?"), COUNT(*) FROM company GROUP BY 1'):
        по_базам[б] = n
инн_база = {}
if база_к:
    инн_база = {str(и): (б or '?') for и, б in цб.execute(f'SELECT inn, {база_к} FROM company')}
цб.close()
print(f'компаний в снимке: {всего}; по базам: {dict(по_базам) or "колонки base нет"}')

пр = sqlite3.connect(f'file:{ПР}?mode=ro', uri=True, timeout=20)
кх = [c[1] for c in пр.execute('PRAGMA table_info(hidden_item)')]
print('колонки hidden_item:', кх)
строки = list(пр.execute("SELECT inn, COALESCE(reason,''), COALESCE(kind,''), "
                         "COALESCE(created_at,'') FROM hidden_item WHERE kind='company'"))
print(f'\nСКРЫТО предприятий: {len(строки)}')
прич = Counter()
по_дате = Counter()
по_базе_скрыт = Counter()
for и, р, к, ts in строки:
    ключ = р.split(':')[0].split('(')[0].strip().lower()[:46] or '(без причины)'
    прич[ключ] += 1
    по_дате[str(ts)[:10]] += 1
    по_базе_скрыт[инн_база.get(str(и), '?')] += 1
print('\nпо ПРИЧИНАМ:')
for р, n in прич.most_common(12):
    print(f'  {n:5}  {р}')
print('\nпо ДАТАМ скрытия:')
for д, n in sorted(по_дате.items()):
    print(f'  {д or "(без даты)"}  {n}')
if инн_база:
    print('\nпо БАЗАМ (какой базы предприятие):')
    for б, n in по_базе_скрыт.most_common():
        видимо = по_базам.get(б, 0) - n
        print(f'  {б}: скрыто {n}, осталось видимыми ~{видимо} из {по_базам.get(б,0)}')
пр.close()
