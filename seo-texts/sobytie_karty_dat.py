# -*- coding: utf-8 -*-
"""Достать НАСТОЯЩИЕ даты карточек источника для строк signals (сервер владельца).

Две вещи, которых нет в базе, но которые лежат на расстоянии одного запроса:
  1. дата поста ВК. `col_vk` берёт `p['date']` (unix-штамп), проверяет им свежесть в
     `fresh_ts(...)` и ВЫБРАСЫВАЕТ: в item кладётся `'pubDate': ''`. Пост никуда не делся -
     `wall.getById` отдаёт его вместе с датой, до 100 постов за вызов;
  2. `seen_news.ts` - когда ссылку впервые увидел конвейер. Это НЕ дата публикации, а дата
     взятия, и помечается именно так.

Аргумент: список rowid через запятую. Пишет результат на дроп (3s_karty_dat.json) и
печатает сводку. В enrich.db НИЧЕГО не пишет.
"""
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request

sys.path.insert(0, r'C:\sender\server')

# ВАЖНО: `import news_scan` ставит ГЛОБАЛЬНЫЙ opener с SOCKS-прокси для обхода сайтов, и
# после этого любой urlopen идёт через прокси. Дроп и api.vk.com через него запрещены
# правилом («Connection not allowed by ruleset») - на этом прогон и умер в первый раз.
# Поэтому свои запросы шлём СОБСТВЕННЫМ опенером без прокси.
BEZ_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))

BAZA = r'C:\sender\enrich.db'
ridy = [int(x) for x in (sys.argv[1] if len(sys.argv) > 1 else '').split(',') if x.strip()]
print('запрошено строк: %d' % len(ridy))

con = sqlite3.connect('file:%s?mode=ro' % BAZA, uri=True)
cur = con.cursor()
cur2 = con.cursor()          # ОТДЕЛЬНЫЙ курсор: вложенный execute на том же курсоре
                             # обрывает внешний цикл после первой строки (проверено -
                             # в разведке 3 из-за этого «сверилась» ровно одна ссылка)

zapisi = {}
for rid in ridy:
    r = cur.execute('SELECT rowid, source, source_url, ts FROM signals WHERE rowid=?', (rid,)).fetchone()
    if r:
        zapisi[rid] = {'source': r[1], 'url': r[2] or '', 'ts': r[3] or ''}

# ---- seen_news
try:
    import news_scan as NS
    norm = NS._norm_url
except Exception:  # noqa: BLE001
    def norm(u):
        u = (u or '').split('#')[0]
        u = re.sub(r'^https?://', '', u).lstrip('www.')
        return u.rstrip('/?&').lower()

nashli_seen = 0
for rid, z in zapisi.items():
    k = norm(z['url'])
    if not k:
        continue
    row = cur2.execute('SELECT ts FROM seen_news WHERE k=?', (k,)).fetchone()
    if row and row[0]:
        z['seen_ts'] = row[0]
        nashli_seen += 1
print('seen_news: нашлось %d из %d' % (nashli_seen, len(zapisi)))

# ---- карточки ВК
VK_RE = re.compile(r'vk\.com/wall(-?\d+)_(\d+)')
tok = os.environ.get('VK_TOKEN', '')
posty = {}
for rid, z in zapisi.items():
    m = VK_RE.search(z['url'])
    if m:
        posty['%s_%s' % (m.group(1), m.group(2))] = rid
print('ВК-постов в выборке: %d, токен: %s' % (len(posty), 'есть' if tok else 'НЕТ'))

nashli_vk = 0
oshibki = []
kluchi = list(posty)
for i in range(0, len(kluchi), 100):
    kusok = kluchi[i:i + 100]
    api = ('https://api.vk.com/method/wall.getById?posts=' + ','.join(kusok)
           + '&access_token=%s&v=5.199' % tok)
    d = {}
    for att in range(3):
        try:
            with BEZ_PROXY.open(urllib.request.Request(
                    api, headers={'User-Agent': 'curl/8.5.0'}), timeout=60) as r:
                d = json.loads(r.read().decode('utf-8', 'replace'))
        except Exception as ex:  # noqa: BLE001
            oshibki.append(repr(ex)[:90])
            time.sleep(1.5 * (att + 1))
            continue
        if (d.get('error') or {}).get('error_code') in (6, 29):
            time.sleep(2 * (att + 1))
            continue
        break
    if d.get('error'):
        oshibki.append('VK error %s' % json.dumps(d['error'], ensure_ascii=False)[:120])
    resp = d.get('response')
    items = resp.get('items') if isinstance(resp, dict) else resp
    for p in (items or []):
        kl = '%s_%s' % (p.get('owner_id'), p.get('id'))
        rid = posty.get(kl)
        if rid and p.get('date'):
            zapisi[rid]['vk_epoch'] = int(p['date'])
            nashli_vk += 1
print('ВК: дат получено %d из %d, ошибок %d' % (nashli_vk, len(posty), len(oshibki)))
for o in oshibki[:3]:
    print('  ! %s' % o)

# ---- контроль прибора заведомо негодным входом: несуществующий пост
if tok:
    api = ('https://api.vk.com/method/wall.getById?posts=-1_999999999'
           '&access_token=%s&v=5.199' % tok)
    try:
        with BEZ_PROXY.open(urllib.request.Request(
                api, headers={'User-Agent': 'curl/8.5.0'}), timeout=45) as r:
            d = json.loads(r.read().decode('utf-8', 'replace'))
        resp = d.get('response')
        items = resp.get('items') if isinstance(resp, dict) else resp
        print('КОНТРОЛЬ: выдуманный пост -1_999999999 вернул %d карточек (норма 0), ошибка: %s'
              % (len(items or []), (d.get('error') or {}).get('error_msg', 'нет')))
    except Exception as ex:  # noqa: BLE001
        print('КОНТРОЛЬ: выдуманный пост дал исключение %r (тоже не дата)' % (ex,))

vyhod = {str(rid): {k: v for k, v in z.items() if k in ('vk_epoch', 'seen_ts')}
         for rid, z in zapisi.items()}
telo = json.dumps(vyhod, ensure_ascii=False).encode('utf-8')
# печатаем ДО отправки: если дроп не возьмёт, данные всё равно доедут хвостом вывода
print('\n#DANNYE#' + telo.decode('utf-8'))
req = urllib.request.Request(
    os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
    + '/3s_karty_dat.json', data=telo, method='PUT',
    headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', ''),
             'Content-Type': 'application/json'})
try:
    with BEZ_PROXY.open(req, timeout=120) as r:
        print('на дроп 3s_karty_dat.json: статус %s, %d байт' % (r.status, len(telo)))
except Exception as ex:  # noqa: BLE001
    print('дроп не взял (%r) - данные выше в #DANNYE#' % (ex,))

print('\n=== ИТОГ: строк %d, дат ВК %d, seen_news %d ===' % (len(zapisi), nashli_vk, nashli_seen))
con.close()
