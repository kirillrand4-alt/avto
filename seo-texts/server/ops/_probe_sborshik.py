# -*- coding: utf-8 -*-
"""Как запускается build_centro_db.py: аргументы, входные файлы, куда пишет."""
import re
п = r'C:\seostat\app\tools\build_centro_db.py'
т = open(п, encoding='utf-8', errors='replace').read()
print('строк:', т.count('\n'))
for m in re.finditer(r'add_argument\(([^)]*)\)', т):
    print('  арг:', re.sub(r'\s+', ' ', m.group(1))[:120])
print('\nупоминания файлов:')
for f in sorted(set(re.findall(r'[\w\-]+\.(?:csv|db|md)', т))):
    print('   ', f)
print('\nусловие запуска / main:')
for m in re.finditer(r'^(?:def main|if __name__).*$', т, re.M):
    print('  ', m.group(0)[:90])
print('\nпервые строки докстринга:')
print('\n'.join(т.split('\n')[:14]))
