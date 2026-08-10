# -*- coding: utf-8 -*-
"""Кладёт журнал съёмки доказательств на дроп, чтобы принять его в park.db.

Съёмка идёт на сервере и пишет C:\\sender\\park_dokaz.jsonl с fsync (durable). В park.db
песочницы лежит только то, что принято до последнего рестарта контейнера, — счёт разошёлся
(357 в базе против нескольких тысяч снятых), и панель показывает снимок не у всех фактов.

Через stdout раннера журнал не забрать: он отдаёт только ХВОСТ вывода — проверено, ушло
7 КБ из мегабайта. Зато хранилище дропа — папка на этом же сервере, поэтому просто копируем
файл туда; токен дропа при этом никуда не уезжает.

Папка найдена замером, а не догадкой: первая попытка легла в C:\\sender\\server (там лежат
файлы с теми же именами, что в списке дропа) и дроп отдал по ней 404 — совпадали имена, а
не папки. Настоящее хранилище — C:\\seostat\\drop\\drop-storage, в нём 8 027 файлов против
8 010 в ответе `list`.
"""
import io, json, os, shutil, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
PUT = r'C:\sender\park_dokaz.jsonl'
DROP = r'C:\seostat\drop\drop-storage\PARK-DOKAZ-SNIMKI-1S.jsonl'
# убрать копию, легшую мимо хранилища на первой попытке
try:
    os.remove(r'C:\sender\server\PARK-DOKAZ-SNIMKI-1S.jsonl')
except OSError:
    pass
if not os.path.exists(PUT):
    print(json.dumps({'oshibka': 'журнала нет на сервере', 'put': PUT}, ensure_ascii=False))
    raise SystemExit(0)
vsego = sdelano = 0
for ln in open(PUT, encoding='utf-8', errors='replace'):
    if not ln.strip():
        continue
    vsego += 1
    if '"снимок сделан"' in ln:
        sdelano += 1
# копия целиком: разбор и отсев — на стороне песочницы, тут только доставка
shutil.copyfile(PUT, DROP + '.tmp')
os.replace(DROP + '.tmp', DROP)
print(json.dumps({'strok_v_zhurnale': vsego, 'snimok_sdelan': sdelano,
                  'bayt': os.path.getsize(DROP), 'polozheno': os.path.basename(DROP)},
                 ensure_ascii=False))
