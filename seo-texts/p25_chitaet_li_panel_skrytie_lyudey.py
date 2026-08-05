# -*- coding: utf-8 -*-
"""Читает ли панель скрытие людей. Запись без чтения — это запись в стол.

Ключ я уже знаю: сосед скрывает человека строкой `hidden_item(inn, 'person', id_записи)`
в `centro_sales.db`. Но знать, куда кладут, мало: если панель нигде не вычитает
скрытых ЛЮДЕЙ при показе карточки, строка ляжет в таблицу, а крестики на витрине
останутся. Проверять надо чтение, а не запись.

Прибор ищет в исходниках панели два места:
  * где `hidden_item` читается с видом `person` — это и есть вычитание;
  * где панель отдаёт людей карточки (SELECT из person) — и стоит ли рядом отбор.
Печатает найденное с именем файла и строкой. Ничего не пишет.
"""
import collections
import io
import json
import os
import re

KORNI = (r'C:\sender\server', r'C:\sender\web\src', r'C:\sender\web', r'C:\sender')
MOYO = re.compile(r'[\\/](?:_ops|_bak[^\\/]*)[\\/]|[\\/][123]s_|_[123]s\.py$', re.I)
RASSH = ('.py', '.js', '.jsx', '.ts', '.tsx', '.html')
CHTENIE = re.compile(r"hidden_item[^\n]{0,120}person|person[^\n]{0,80}hidden_item", re.I)
VYDACHA = re.compile(r"(?:from|FROM)\s+person\b", re.I)
KRESTIK = re.compile(r"kind\s*[:=]\s*['\"]person['\"]", re.I)

sch = collections.Counter()
chtenie, vydacha, krestik = [], [], []
seen = set()
for koren in KORNI:
    for put, papki, fayly in os.walk(koren):
        if re.search(r'[\\/](?:node_modules|\.git|__pycache__)[\\/]', put + os.sep):
            papki[:] = []
            continue
        for f in fayly:
            if not f.lower().endswith(RASSH):
                continue
            p = os.path.join(put, f)
            if MOYO.search(p) or p in seen:
                continue
            seen.add(p)
            try:
                if os.path.getsize(p) > 6 * 1024 * 1024:
                    continue
                t = io.open(p, encoding='utf-8', errors='replace').read()
            except Exception:  # noqa: BLE001
                continue
            for rg, kuda, imya in ((CHTENIE, chtenie, 'чтение скрытия людей'),
                                   (KRESTIK, krestik, 'крестик «скрыть человека»'),
                                   (VYDACHA, vydacha, 'выдача людей карточки')):
                for m in rg.finditer(t):
                    n = t[:m.start()].count('\n') + 1
                    kuda.append((p[-58:], n, t.split('\n')[n - 1].strip()[:140]))
                    sch[imya] += 1
                    if len(kuda) > 40:
                        break

for imya, sp in (('ЧИТАЕТ ЛИ скрытие людей', chtenie),
                 ('крестик «скрыть человека» в интерфейсе', krestik),
                 ('выдача людей карточки', vydacha)):
    print('\n=== %s — %d' % (imya, len(sp)))
    for p, n, s in sp[:14]:
        print('  %s:%-5d %s' % (p, n, s))
    if not sp:
        print('  НЕ НАЙДЕНО')

for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({'читает скрытие людей': bool(chtenie),
                            'крестик есть': bool(krestik)}, ensure_ascii=False))
