# -*- coding: utf-8 -*-
"""Показать файл сервера целиком. Читает, не трогает.

Нужен, чтобы взять ЧУЖОЕ правило как есть. `_skryt2.py` написан не мной — им соседняя
сессия скрывает людей в панели. Ключ скрытия угадывать нельзя: угаданный ключ ляжет в
таблицу, ни с чем не совпадёт, и панель покажет то же самое, а я отчитаюсь о чистых
данных. Поэтому смотрю глазами, каким ключом скрывают, и повторяю его в точности.

Запуск: python3 p25_pokazat_fayl.py <путь> [ещё путь ...]
"""
import io
import json
import os
import sys

puti = sys.argv[1:] or [r'C:\sender\server\ops\_skryt2.py']
pokazano = 0
for p in puti:
    print('\n===== %s' % p)
    if not os.path.exists(p):
        print('  файла нет')
        continue
    try:
        t = io.open(p, encoding='utf-8', errors='replace').read()
    except Exception as e:  # noqa: BLE001
        print('  не прочитался: %s' % e)
        continue
    for i, s in enumerate(t.split('\n')[:200], 1):
        print('%4d| %s' % (i, s[:150]))
    pokazano += 1
print('ИТОГ ' + json.dumps({'показано файлов': pokazano}, ensure_ascii=False))
