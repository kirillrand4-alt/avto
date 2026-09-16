# -*- coding: utf-8 -*-
"""Проба 16: импортируем УЖЕ ЗАЛИТЫЙ C:\\sender\\_tmp\\collector_egrz.py как модуль
(заодно проверка «импорт без побочных эффектов») и гоняем полную выборку
+ фильтр по региону + короткое окно. Важное — В КОНЦЕ."""
import importlib.util
import os
import time

PATH = r'C:\sender\_tmp\collector_egrz.py'
print('модуль на месте:', os.path.exists(PATH), os.path.getsize(PATH) if os.path.exists(PATH) else 0)

spec = importlib.util.spec_from_file_location('collector_egrz', PATH)
C = importlib.util.module_from_spec(spec)
t0 = time.time()
spec.loader.exec_module(C)
print('импорт занял %.2f с (побочных эффектов/сетевых вызовов при импорте нет)'
      % (time.time() - t0))

# 1. полная выборка за 90 дней
t = time.time()
full = C.col_egrz(days=90, max_items=5000, verbose=True)
t_full = time.time() - t
inn = sum(1 for i in full if i['inn'])
roles = {}
stages = set()
for i in full:
    roles[i['company_role']] = roles.get(i['company_role'], 0) + 1
    stages.add(i['stage'])
noname = [i for i in full if not i['company_name']]

# 2. фильтр по региону (коды 22 Алтайский край, 34 Волгоградская) и по названию
t = time.time()
reg = C.col_egrz(days=90, max_items=500, regions=['22', '34'])
reg_names = sorted({i['region'] for i in reg})
t_reg = time.time() - t

t = time.time()
reg2 = C.col_egrz(days=90, max_items=200, regions=['Московская область'])
reg2_names = sorted({i['region'] for i in reg2})
t_reg2 = time.time() - t

# 3. короткое окно + жёсткий гейт по производственной лексике
short = C.col_egrz(days=14, max_items=500)
hard = C.col_egrz(days=14, max_items=500, require_prod_kw=True)

# 4. энергетический профиль (опциональные разделы)
energo = C.col_egrz(days=90, max_items=100, sections=C.SECTIONS_ENERGO)

# 5. контракт item
keys_ok = True
need = {'title', 'link', 'pubDate', 'source', 'tier', 'collector', 'query',
        'company_name', 'inn', 'sum', 'region', 'stage'}
for i in full[:50]:
    if not need.issubset(set(i)):
        keys_ok = False

print()
print('==================== ИТОГ ====================')
print('контракт item (title/link/pubDate/source/tier/collector/query + company_name/inn/sum/'
      'region/stage) соблюдён:', keys_ok)
print('стадии в выдаче:', stages)
print('роли компании:', roles)
print('без имени компании: %d' % len(noname))
print('регионы при regions=[22,34]: %s (%d шт, %.1f с)' % (reg_names, len(reg), t_reg))
print('регионы при regions=[Московская область]: %s (%d шт, %.1f с)'
      % (reg2_names, len(reg2), t_reg2))
print('за 14 дней: %d; с жёстким гейтом лексики: %d' % (len(short), len(hard)))
print('разделы энергетики (05./котельные) за 90 дней: %d' % len(energo))
print('ПОЛНАЯ ВЫБОРКА за 90 дней: %d заключений, с ИНН %d (%.0f%%), время %.1f с'
      % (len(full), inn, 100.0 * inn / max(1, len(full)), t_full))
