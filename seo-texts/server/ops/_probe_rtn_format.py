# -*- coding: utf-8 -*-
"""Почему из 40 файлов на 349 тысяч символов вышло НОЛЬ строк.

Разбор графиков РТН держится на одной регулярке, которая ждёт строго такой
порядок: номер, ФИО с заглавных, должность со строчной, запятая, организация.
Файлов в потоке 942, разобрано в строки — малая часть. Ноль строк при трёхстах
тысячах прочитанных символов означает, что формат другой, а не что файл пуст.

Считаем: сколько файлов дали ноль строк, и показываем НАЧАЛО их текста
дословно — по нему и надо строить второй шаблон. Ничего не пишем.
"""
import io
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\server\ops')
import enrich_contacts as EC   # noqa: E402
import rtn_znaniya as RTN      # noqa: E402

П_СТРОКИ = RTN.П_СТРОКИ
П_ССЫЛКИ = RTN.П_ССЫЛКИ

пусто, есть = [], 0
итог = Counter()
for ln in io.open(П_СТРОКИ, encoding='utf-8', errors='replace'):
    try:
        d = json.loads(ln)
    except Exception:  # noqa: BLE001
        continue
    n = len(d.get('строки') or [])
    if d.get('пусто'):
        итог['файл не прочитался вовсе'] += 1
        continue
    if n:
        есть += 1
        итог['строки извлеклись'] += 1
    else:
        итог['текст есть, строк ноль'] += 1
        пусто.append(d.get('файл') or '')

всего_ссылок = 0
if os.path.exists(П_ССЫЛКИ):
    for ln in io.open(П_ССЫЛКИ, encoding='utf-8', errors='replace'):
        всего_ссылок += 1

# берём три «нулевых» файла и показываем их текст дословно
образцы = []
for у in пусто[:3]:
    try:
        т = EC.doc_text(у) or ''
    except Exception as e:  # noqa: BLE001
        образцы.append({'url': у, 'ошибка': str(e)[:80]})
        continue
    # сжимаем повторные пробелы, но НЕ переводы строк — важна раскладка
    т = re.sub(r'[ \t\u00a0]+', ' ', т)
    образцы.append({'url': у[:110], 'символов': len(т),
                    'первые_1800': т[:1800]})

print(json.dumps({
    'ссылок_на_файлы_в_потоке': всего_ссылок,
    'файлов_разобрано': sum(итог.values()),
    'разбор': итог.most_common(),
    'образцы_нулевых': образцы,
}, ensure_ascii=False, indent=1)[:9000])
