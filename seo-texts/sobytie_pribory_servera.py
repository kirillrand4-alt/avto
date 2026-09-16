# -*- coding: utf-8 -*-
"""Разведка 4: чем на сервере звать провайдера, есть ли токен ВК и как устроен ключ seen_news.

Нужно для двух вещей:
  1) классификатор стадии должен уметь работать И в песочнице (gen_provider), И на сервере
     (там своего gen_provider нет, новости зовут провайдера через verify_company);
  2) дата ВК-поста лежит в карточке источника (wall.getById), а в сигнал не доехала -
     надо знать, есть ли токен.

Прибор только читает.
"""
import inspect
import os
import re
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')

try:
    import verify_company as VC  # noqa: E402
    print('verify_company = %s' % VC.__file__)
    print('модель по умолчанию: %r' % getattr(VC, '_PROVIDER_MODEL', None))
    src = inspect.getsource(VC._provider_call_stdlib)
    print('\n##### _provider_call_stdlib (%d строк)' % len(src.split('\n')))
    for l in src.split('\n')[:80]:
        print('   ' + l[:112])
except Exception as ex:  # noqa: BLE001
    print('verify_company не прочитан: %r' % (ex,))

print('\n##### токены в окружении сервера (только наличие)')
for k in ('VK_TOKEN', 'DADATA_TOKEN', 'PROVIDER_API_KEY', 'PROVIDER_BASE_URL', 'ROUTER_KEY'):
    v = os.environ.get(k)
    print('  %-18s %s' % (k, 'есть' if v else 'нет'))

try:
    import news_scan as NS  # noqa: E402
    print('\n_norm_url:')
    for l in inspect.getsource(NS._norm_url).split('\n')[:20]:
        print('   ' + l[:112])
except Exception as ex:  # noqa: BLE001
    print('news_scan._norm_url: %r' % (ex,))

con = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True)
cur = con.cursor()
print('\n##### seen_news: сходятся ли ключи со ссылками signals')
pr = cur.execute('SELECT k, ts FROM seen_news ORDER BY rowid DESC LIMIT 3').fetchall()
for k, t in pr:
    print('  %s   %s' % (k[:70], t))
# прямая проверка совпадения: нормализуем url сигнала как news_scan и ищем в seen_news
try:
    import news_scan as NS
    n = 0
    sovpalo = 0
    for (u,) in cur.execute("SELECT source_url FROM signals WHERE ts IS NULL OR TRIM(ts)='' LIMIT 300"):
        n += 1
        k = NS._norm_url(u or '')
        if k and cur.execute('SELECT 1 FROM seen_news WHERE k=?', (k,)).fetchone():
            sovpalo += 1
    print('  из %d бездатных ссылок нашлось в seen_news: %d' % (n, sovpalo))
except Exception as ex:  # noqa: BLE001
    print('  сверка не прошла: %r' % (ex,))

print('\n##### индексы на signals (чтобы новая таблица легла в том же стиле)')
for r in cur.execute("SELECT name, sql FROM sqlite_master WHERE tbl_name='signals'"):
    print('  %s : %s' % (r[0], (r[1] or '')[:180]))
con.close()
print('\n=== ИТОГ разведки 4 ===')
