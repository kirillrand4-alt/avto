# -*- coding: utf-8 -*-
"""Ссылка на статистику в шапке главной страницы копии (там, куда админ приземляется).

Шаблон главной называется не centro_sales.html — ищу его по ссылке на /centro/admin,
а не по угаданному имени.
"""
import io
import os
import re

KAT = r'C:\centro2\app\templates'
spisok = sorted(f for f in os.listdir(KAT)
                if f.endswith('.html') and 'centro' in f.lower())
print('шаблоны centro*: %s' % ', '.join(spisok))

nashlos = []
for f in spisok:
    put = os.path.join(KAT, f)
    t = io.open(put, encoding='utf-8').read()
    est_admin = '/centro/admin' in t
    est_stats = '/centro/stats' in t
    print('  %-26s %7d знаков, ссылка на admin: %-3s на stats: %s'
          % (f, len(t), 'да' if est_admin else 'нет', 'да' if est_stats else 'нет'))
    if est_admin and not est_stats:
        nashlos.append((f, put))

sdelano = 0
for f, put in nashlos:
    t = io.open(put, encoding='utf-8').read()
    # Ставлю ровно рядом с уже существующей ссылкой на распределение: так новая кнопка
    # окажется в той же шапке и в том же стиле, без догадок про вёрстку.
    m = re.search(r'<a[^>]*href="\{\{\s*base_path\s*\}\}/centro/admin"[^>]*>.*?</a>', t, re.S)
    if not m:
        print('%s: ссылка на admin есть, но её тег не распознан — пропускаю' % f)
        continue
    novo = m.group(0) + '<a href="{{ base_path }}/centro/stats">Статистика</a>'
    io.open(put, 'w', encoding='utf-8').write(t[:m.start()] + novo + t[m.end():])
    sdelano += 1
    print('%s: ссылка на статистику добавлена рядом с «%s»'
          % (f, re.sub(r'<[^>]+>', '', m.group(0)).strip()))

print('\n===== ИТОГ =====')
print('правок внесено: %d из %d' % (sdelano, len(nashlos)))
for f in spisok:
    t = io.open(os.path.join(KAT, f), encoding='utf-8').read()
    if '/centro/admin' in t or '/centro/stats' in t:
        print('%-26s stats: %s' % (f, 'ЕСТЬ' if '/centro/stats' in t else 'НЕТ'))
