# -*- coding: utf-8 -*-
"""Который из двух сборщиков создал ТЕКУЩУЮ базу панели.

Два кандидата в разных территориях: C:\\sender\\_ops (моя) и C:\\seostat\\app\\tools
(приложение панели). Сказать «наверное мой» нельзя — надо сверить состав
таблиц и то, из каких файлов сборщик читает.
"""
import os
import re
import sys

sys.path.insert(0, r'C:\seostat')
from app.services import centro_catalog  # noqa: E402

КАНД = [r'C:\seostat\app\tools\build_centro_db.py',
        r'C:\sender\_ops\build_centrifugal_db.py']


def main():
    with centro_catalog.connect() as conn:
        табл = sorted(r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall())
    print('таблицы текущей базы:', ', '.join(табл))
    for п in КАНД:
        if not os.path.exists(п):
            print(f'\n{п}: НЕТ')
            continue
        т = open(п, encoding='utf-8', errors='replace').read()
        создаёт = sorted(set(re.findall(
            r'CREATE TABLE(?:\s+IF NOT EXISTS)?\s+(\w+)', т)))
        читает = sorted(set(re.findall(r"['\"]([\w\-]+\.csv)['\"]", т)))[:10]
        совпало = set(создаёт) & set(табл)
        print(f'\n{п}')
        print(f'  создаёт таблицы: {", ".join(создаёт) or "—"}')
        print(f'  совпадение с текущей базой: {len(совпало)} из {len(табл)}')
        print(f'  читает файлы: {", ".join(читает) or "—"}')


if __name__ == '__main__':
    main()
