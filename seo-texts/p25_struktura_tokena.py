# -*- coding: utf-8 -*-
"""Разобрать СТРУКТУРУ токен-файла построчно, не печатая значений. Чтобы войти правильно.

Вход Basic не прошёл: мой разбор не нашёл в файле пары логин:пароль. Значит формат иной,
чем я предположила. Печатаю по каждой строке только МЕТКУ (левую часть до разделителя) и
длину остатка — по этому видно, где логин и где пароль, а сам пароль остаётся тайной.
"""
import io
import json
import os
import re

P = r'C:\sender\_ops\p25_user3_token.txt'
if not os.path.exists(P):
    print('файла нет'); raise SystemExit

syroy = io.open(P, encoding='utf-8', errors='replace').read()
print('всего длина %d, строк %d' % (len(syroy.strip()), syroy.count('\n') + 1))
for i, s in enumerate(syroy.split('\n'), 1):
    st = s.strip()
    if not st:
        print('  %d| (пусто)' % i)
        continue
    razd = ':' if ':' in st else ('=' if '=' in st else '')
    if razd:
        levo, _, pravo = st.partition(razd)
        # Левая часть это метка (логин/пароль/название) — печатаю. Правую только меряю.
        # Но если левая сама выглядит как секрет (длинная, без пробелов) — не печатаю.
        levo_pokaz = levo.strip() if (len(levo.strip()) <= 16 or ' ' in levo.strip()) \
            else '<длинное, скрыто>'
        print('  %d| метка «%s» %s остаток длиной %d, в остатке пробелов %d'
              % (i, levo_pokaz, razd, len(pravo.strip()), pravo.strip().count(' ')))
    else:
        # Строка без разделителя: печатаю длину и есть ли пробелы (описание vs токен).
        print('  %d| без разделителя, длина %d, пробелов %d, только-словарные символы: %s'
              % (i, len(st), st.count(' '),
                 bool(re.fullmatch(r'[A-Za-z0-9+/=_\-]+', st))))
print('ИТОГ ' + json.dumps({'разобрано строк': syroy.count(chr(10)) + 1},
                           ensure_ascii=False))
