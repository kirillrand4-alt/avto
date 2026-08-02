# -*- coding: utf-8 -*-
"""Какие колонки читает сборщик из summary/details/contacts.

Если подсунуть ему файл с другими именами колонок, он соберёт ПУСТУЮ базу и
не пожалуется: csv.DictReader на отсутствующем ключе отдаёт None. Поэтому
имена вытаскиваем из кода, а не угадываем по своему файлу.
"""
import re
т = open(r'C:\seostat\app\tools\build_centro_db.py', encoding='utf-8',
         errors='replace').read()
блоки = re.split(r'\ndef ', т)
for б in блоки:
    имя = б.split('(')[0].strip()
    поля = sorted(set(re.findall(r'(?:row|r|item|rec)(?:\.get\(|\[)["\']([\w]+)["\']', б)))
    if поля:
        print(f'--- {имя[:44]}')
        print('   ', ', '.join(поля))
print('\nразделы, которые ищет в details:')
for m in sorted(set(re.findall(r'["\']([А-ЯЁ]{4,})["\']', т))):
    print('   ', m)
