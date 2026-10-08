# -*- coding: utf-8 -*-
"""Где в копии панели длинные тире: код (строки, не комментарии), шаблоны (сравнения), статика, данные."""
import io
import os
import re
import sqlite3
import tokenize

KOREN = r'C:\centro2'
APP = os.path.join(KOREN, 'app')
DL = '\u2014'
out = []

# код: только строковые литералы (tokenize), без комментариев и докстрингов-модулей не различаю
for d, _, fs in os.walk(APP):
    for f in fs:
        p = os.path.join(d, f)
        if f.endswith('.py'):
            try:
                toks = list(tokenize.generate_tokens(io.open(p, encoding='utf-8').readline))
            except Exception as e:
                out.append('!! %s %s' % (p, e))
                continue
            for t in toks:
                if t.type == tokenize.STRING and DL in t.string:
                    s = t.string
                    if s.startswith(('"""', "'''", 'r"""', "r'''")) and len(s) > 200:
                        continue  # докстринги
                    out.append('PY %s:%d %s' % (os.path.relpath(p, APP), t.start[0], s[:150].replace('\n', ' ')))
        elif f.endswith(('.js', '.css')):
            n = io.open(p, encoding='utf-8', errors='replace').read().count(DL)
            if n:
                out.append('STATIC %s %d' % (os.path.relpath(p, APP), n))
        elif f.endswith('.html'):
            t = io.open(p, encoding='utf-8').read()
            for m in re.finditer(r'[!=]=\s*[\'"]%s[\'"]|[\'"]%s[\'"]\s*[!=]=|[\'"]%s[\'"]\s+(not\s+)?in\b' % (DL, DL, DL), t):
                out.append('TPLCMP %s:%d %s' % (f, t[:m.start()].count('\n') + 1, t[max(0, m.start() - 60):m.end() + 20].replace('\n', ' ')))
            out.append('TPL %s %d' % (f, t.count(DL)))

k = sqlite3.connect(os.path.join(KOREN, 'data', 'meyer_baza1.db'))
for (tabl,) in k.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'").fetchall():
    for r in k.execute('PRAGMA table_info("%s")' % tabl).fetchall():
        kol = r[1]
        try:
            n = k.execute('select count(*) from "%s" where instr("%s", ?)>0' % (tabl, kol), (DL,)).fetchone()[0]
        except Exception:
            continue
        if n:
            out.append('DATA %s.%s %d (тип %s)' % (tabl, kol, n, r[2]))
s = sqlite3.connect(os.path.join(KOREN, 'data', 'centro_sales_meyer1.db'))
for (tabl,) in s.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'").fetchall():
    for r in s.execute('PRAGMA table_info("%s")' % tabl).fetchall():
        try:
            n = s.execute('select count(*) from "%s" where instr("%s", ?)>0' % (tabl, r[1]), (DL,)).fetchone()[0]
        except Exception:
            continue
        if n:
            out.append('SALES %s.%s %d' % (tabl, r[1], n))
t = '\n'.join(out)
io.open(r'C:\seostat\drop\drop-storage\centro2-tire-probe.txt', 'w', encoding='utf-8').write(t)
print(t[-5000:])
print('строк: %d' % len(out))
