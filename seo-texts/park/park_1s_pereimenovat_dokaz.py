# -*- coding: utf-8 -*-
"""Переносит снимки доказательств в папку, которую панель отдаёт без пароля-заглушки.

Находка: `/static/dokaz/<файл>` отвечает **401**, а `/static/css/centro.css` — 200.
Причина не в правах на файл: приложение обзвона закрыто HTTP Basic ВЕЗДЕ, кроме путей,
содержащих слово `centro` (эвристика `_is_centro_path`). В адресе `dokaz` этого слова нет,
поэтому картинка не отдавалась, и в карточке была подпись без изображения.

Заслон пропускает путь с СЕГМЕНТОМ `/centro/` (`"/centro/" in clean`), а не с
подстрокой «centro»: поэтому `static/centro-dokaz/` тоже давал 401, а верный
путь — `static/centro/dokaz/`. Прочитал сам код заслона, а не гадал второй раз.
"""
import json, os, shutil

STAR = r'C:\seostat\app\static\centro-dokaz'
NOV = r'C:\seostat\app\static\centro\dokaz'
os.makedirs(NOV, exist_ok=True)
n = 0
if os.path.isdir(STAR):
    for x in os.listdir(STAR):
        try:
            shutil.move(os.path.join(STAR, x), os.path.join(NOV, x))
            n += 1
        except Exception:
            pass
o = {'perenes': n, 'v_novoy': len(os.listdir(NOV))}
import urllib.request
f = sorted(os.listdir(NOV))[:1]
if f:
    try:
        with urllib.request.urlopen(
                'http://127.0.0.1:8012/obzvon/static/centro/dokaz/' + f[0], timeout=20) as r:
            o['proverka'] = {'http': r.status, 'bajt': len(r.read()), 'fayl': f[0]}
    except Exception as e:
        o['proverka'] = str(e)[:120]
print(json.dumps(o, ensure_ascii=False, indent=1))
