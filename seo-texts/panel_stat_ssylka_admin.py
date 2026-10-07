# -*- coding: utf-8 -*-
"""Проверка и починка ссылки на статистику в шапке админки копии.

Предыдущий скрипт напечатал «ссылка добавлена», но напечатал это по факту ЗАПИСИ файла,
а не по факту срабатывания замены: str.replace без совпадения возвращает ту же строку и
не жалуется. Поэтому здесь сперва показывается настоящее содержимое шапки, и только
потом, если ссылки нет, она ставится по реально существующему якорю.
"""
import io
import os
import re

KOREN = r'C:\centro2'
FAJLY = {
    'centro_admin.html': os.path.join(KOREN, 'app', 'templates', 'centro_admin.html'),
    'centro_sales.html': os.path.join(KOREN, 'app', 'templates', 'centro_sales.html'),
}

for imya, put in FAJLY.items():
    if not os.path.exists(put):
        print('%s: файла нет' % imya)
        continue
    t = io.open(put, encoding='utf-8').read()
    shapka = re.search(r'<header.*?</header>', t, re.S)
    print('\n===== %s (%d знаков)' % (imya, len(t)))
    print('ссылка на /centro/stats: %s' % ('ЕСТЬ' if '/centro/stats' in t else 'НЕТ'))
    if shapka:
        print('шапка как есть:')
        for l in shapka.group(0).splitlines():
            if l.strip():
                print('   %s' % l.strip())
    else:
        print('тега <header> нет; первые строки body:')
        b = re.search(r'<body.*?>(.{0,600})', t, re.S)
        print('   %s' % re.sub(r'\s+', ' ', b.group(1)).strip() if b else '   ?')

# --- починка: ставим ссылку сразу после открывающего <header ...>
SSYLKA = '\n  <a href="{{ base_path }}/centro/stats">Статистика</a>'
for imya, put in FAJLY.items():
    if not os.path.exists(put):
        continue
    t = io.open(put, encoding='utf-8').read()
    if '/centro/stats' in t:
        print('\n%s: ссылка уже на месте, не трогаю' % imya)
        continue
    m = re.search(r'<header[^>]*>', t)
    if not m:
        print('\n%s: <header> не найден, ссылку НЕ добавила' % imya)
        continue
    t = t[:m.end()] + SSYLKA + t[m.end():]
    io.open(put, 'w', encoding='utf-8').write(t)
    print('\n%s: ссылка добавлена после %s' % (imya, m.group(0)))

print('\n===== ИТОГ =====')
for imya, put in FAJLY.items():
    if os.path.exists(put):
        t = io.open(put, encoding='utf-8').read()
        print('%-20s ссылка на статистику: %s'
              % (imya, 'ЕСТЬ' if '/centro/stats' in t else 'НЕТ'))
