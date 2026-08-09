# -*- coding: utf-8 -*-
"""Те же 25 ссылок, но непроверенные — открыть БРАУЗЕРОМ. Ответ на «если не всё, то доделать».

Простой HTTP-заход дал:

    ДОКАЗЫВАЕТ 12 | ОТКРЫЛАСЬ, НО ИСКОМОГО НЕТ 8 | НЕ ОТКРЫЛАСЬ 5

Тринадцать неподтверждённых — это не тринадцать выдумок. Смотрю, ЧТО именно там стоит:

  • `tender.pro/#/tender/1099290` — адрес с решёткой. Это одностраничное приложение: сервер
    отдаёт каркас, карточку рисует скрипт. Простой запрос её не увидит НИКОГДА, и «искомого
    нет» здесь значит «страница ещё не отрисована». Ровно этим же оказался Портал поставщиков
    Москвы у 1-й сессии.
  • `checko.ru/company/inn/...` — 404 на прямой заход. Это агрегатор с защитой от роботов, а
    не первоисточник; номер оттуда добыт когда-то через другой вход.
  • обычные сайты предприятий — страница живая, номера на ней сейчас нет.

Три случая различаются по смыслу, и разделить их важнее, чем получить красивую долю:
переписывать SPA под браузер — работа; агрегатор — вопрос честной пометки источника;
исчезнувший со страницы номер — потеря, которую надо назвать.

Открываю браузером с сервера (тот же прибор, которым берётся B2B и Росэлторг) и заново
сужу по тому же признаку: есть ли на отрисованной странице то, ради чего ссылка стоит.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import random
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

DIR = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(DIR, 'server', 'run_on_server.py')
POTOKI = [(r'C:\sender\_ops\park_ingest_3.jsonl', 'машина'),
          (r'C:\sender\_ops\PARK-KONTAKTY-3S.jsonl', 'контакт')]
# те же файлы лежат и на дропе — здесь читаю скачанные копии
MESTNYE = [(os.path.join('/home/user/work', 'park_ingest_3.jsonl'), 'машина'),
           (os.path.join('/home/user/work', 'PARK-KONTAKTY-3S.jsonl'), 'контакт')]
TEG = re.compile(r'<[^>]+>')


def klyuch(s):
    return re.sub(r'[\s\-]', '', s or '').upper().replace(',', '.')


stroki = []
for put, chto in MESTNYE:
    if not os.path.exists(put):
        continue
    for s in io.open(put, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        for u in (o.get('istochniki') or '').split(' | '):
            if u.startswith('http'):
                stroki.append({'url': u, 'chto': chto, 'inn': o.get('inn', ''),
                               'iskat': (o.get('napisanie') or o.get('nomer')
                                         or o.get('pochta') or ''),
                               'imya': o.get('imya', '')})
random.seed(825)  # ТОТ ЖЕ жребий, что и в простом заходе
vybor = random.sample(stroki, min(25, len(stroki)))


def brauzer(u):
    args = {'url': u, 'screenshot': False, 'return_html': True, 'html_cap': 900000,
            'wait_ms': 22000, 'card_wait_ms': 8000, 'proxy': False,
            'ignore_https_errors': True}
    try:
        r = subprocess.run([sys.executable, RUNNER, 'browser_probe',
                            json.dumps(args, ensure_ascii=False)],
                           capture_output=True, timeout=600)
    except Exception as e:  # noqa: BLE001
        return '', str(e)[:60]
    s = r.stdout.decode('utf-8', 'replace')
    i = s.find('{')
    if i < 0:
        return '', 'раннер не вернул JSON'
    try:
        d = (json.loads(s[i:]).get('data') or {})
    except Exception:  # noqa: BLE001
        return '', 'битый JSON'
    return d.get('html') or '', str(d.get('error') or '')[:60]


def sudit(z, html):
    text = re.sub(r'\s+', ' ', TEG.sub(' ', html))
    if z['chto'] == 'машина':
        est = any(klyuch(n) in klyuch(text) for n in z['iskat'].split(' | ') if len(n) > 3)
    else:
        c = re.sub(r'\D', '', z['iskat'])
        est = bool(c) and c in re.sub(r'\D', '', text)
        if not est and z['imya']:
            fam = z['imya'].split(' ')[0]
            est = len(fam) > 3 and fam in text
    return est, len(text)


def rabota(z):
    html, err = brauzer(z['url'])
    if not html:
        return z, 'браузер не отдал страницу: %s' % (err or 'пусто'), 0
    est, dl = sudit(z, html)
    return z, ('ДОКАЗЫВАЕТ ПОСЛЕ ОТРИСОВКИ' if est
               else 'отрисовалась (%d знаков), искомого всё равно нет' % dl), dl


with ThreadPoolExecutor(max_workers=4) as ex:
    rez = list(ex.map(rabota, vybor))

ishody = collections.Counter()
print('\n\n########## ТЕ ЖЕ 25 ССЫЛОК, ОТКРЫТЫЕ БРАУЗЕРОМ')
for z, verd, dl in rez:
    dom = re.sub(r'^https?://([^/]+).*', r'\1', z['url'])
    ishody[verd.split('(')[0].split(':')[0].strip()] += 1
    print('  [%s] %-24s %-12s искали «%s»' % (z['chto'], dom[:24], z['inn'], z['iskat'][:24]))
    print('        %s' % verd)
    print('        %s' % z['url'][:140])
print('\n########## ЧИСЛА')
print('  проверено браузером         %4d' % len(rez))
for k, v in ishody.most_common():
    print('     %-52s %4d' % (k[:52], v))
print('ИТОГ ' + json.dumps({'проверено': len(rez),
                            'доказывают после отрисовки':
                                ishody.get('ДОКАЗЫВАЕТ ПОСЛЕ ОТРИСОВКИ', 0)},
                           ensure_ascii=False))
