# -*- coding: utf-8 -*-
"""Очистка drop-сервера: (1) архив производных (тексты+структуры+манифесты) -> на drop,
(2) удаление с drop ТОЛЬКО документов, обработанных локально (есть raw И text).
Медиа (jpg/png/mp4/psd/cdr) НЕ трогаем. Манифесты НЕ трогаем."""
import json, os, subprocess, sys, tarfile

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
from kp_pipeline import drop_list, RAW, TXT, WORK, U, TOK, DOC_EXT

def curl(args, timeout=1800):
    return subprocess.run(['curl', '-s', '-H', f'X-Drop-Token: {TOK}'] + args,
                          capture_output=True, text=True, timeout=timeout).stdout

# 1) архив производных
arc = os.path.join('/tmp', 'kp-derived.tar.gz')
with tarfile.open(arc, 'w:gz') as t:
    for sub in ('text', 'struct'):
        p = os.path.join(WORK, sub)
        if os.path.isdir(p):
            t.add(p, arcname=f'kp-derived/{sub}')
    for f in ('clusters.json', 'kp-manifest.csv', 'kp-manifest-enger.csv'):
        p = os.path.join(WORK, f)
        if os.path.exists(p):
            t.add(p, arcname=f'kp-derived/{f}')
sz = os.path.getsize(arc)
resp = curl(['-T', arc, f'{U}/kp-derived.tar.gz'])
ok = '"ok"' in resp and 'true' in resp
print(f'архив производных: {sz/1e6:.1f} МБ -> drop: {"OK" if ok else "FAIL: " + resp[:100]}', flush=True)
if not ok:
    print('СТОП: без сохранённых производных ничего не удаляю'); sys.exit(1)

# 2) удаление обработанных документов
names = [f['name'] for f in drop_list() if f['name'].startswith('kp') and 'manifest' not in f['name']]
deleted = kept = 0
for n in names:
    ext = n.rsplit('.', 1)[-1].lower()
    if ext not in DOC_EXT:
        kept += 1; continue                     # медиа и прочее не трогаем
    if os.path.exists(os.path.join(RAW, n)) and os.path.exists(os.path.join(TXT, n + '.txt')):
        r = curl(['-X', 'DELETE', f'{U}/{n}'], 60)
        deleted += ('"ok"' in r)
    else:
        kept += 1                                # не обработан - оставляем
print(f'удалено обработанных документов: {deleted} | оставлено (медиа/необработанные): {kept}', flush=True)
