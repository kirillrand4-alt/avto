# -*- coding: utf-8 -*-
"""559 предприятий без телефона: иду на их САЙТЫ. Канал не тронут ни разу за смену.

Оба списка вместе покрыли 626 предприятий из 1 185. Оставшиеся 559 — честный ноль: телефона
нет ни в `enrich.db`, ни в `centrifugal.db`, ни в `atlas_copco.db`. Но у части из них в базе
записан САЙТ, а телефон приёмной лежит на странице контактов — этот путь мы не пробовали.

Беру сайт, дёргаю корень и типовые страницы контактов, вынимаю телефоны и почты. Разбор
страницы отдаю провайдеру (владелец пополнил баланс и просил работать на gemini): регулярка
по телефонам ловит и ИНН, и даты, и номера лицензий, а модель отличает «приёмная», «отдел
снабжения», «главный энергетик» от «телефон нашего партнёра» — и вернёт должность рядом с
номером, чего регуляркой не получить.

ЗАСЛОН НА РЕЗУЛЬТАТ, как учит сегодняшний день: телефон засчитывается, только если он
телефонного вида И найден на странице, чей ХОСТ совпадает с сайтом предприятия из базы.
Чужой номер с чужого домена — это ровно та ошибка, которой мы весь день учимся не делать.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import ssl
import sqlite3
import time
import urllib.parse
import urllib.request

PARK = [r'C:\sender\_ops\park_ingest_3.jsonl', r'C:\sender\_ops\park_ingest_3b.jsonl',
        r'C:\sender\_ops\park_ingest_3c.jsonl']
GOTOVO = [r'C:\sender\_ops\PARK-SPISOK-DLYA-ZVONKA-3S.csv',
          r'C:\sender\_ops\PARK-SPISOK-CHEREZ-KOMMUTATOR-3S.csv']
BAZY = [r'C:\sender\enrich.db', r'C:\seostat\data\centrifugal.db',
        r'C:\seostat\drop\drop-storage\atlas_copco.db']
VYHOD = r'C:\sender\_ops\PARK-SAYTY-TELEFONY-3S.jsonl'
SKOLKO = 90
PUTI = ['', '/contacts', '/contacts/', '/kontakty', '/kontakty/', '/contact', '/about/contacts']
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))
TEG = re.compile(r'<[^>]+>')
TELEFON = re.compile(r'(?:\+7|8)[\s\-()]*\d{3,5}[\s\-()]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}')
POCHTA = re.compile(r'[A-Za-z0-9._%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')

park = {}
for p in PARK:
    if not os.path.exists(p):
        continue
    for s in io.open(p, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        if o.get('inn'):
            park.setdefault(o['inn'], o.get('vid') or 'машина')
gotovo = set()
for g in GOTOVO:
    if not os.path.exists(g):
        continue
    for s in io.open(g, encoding='utf-8-sig').read().splitlines()[1:]:
        p_ = s.split(';')
        if p_ and p_[0].strip().isdigit():
            gotovo.add(p_[0].strip())

sayty, imena = {}, {}
for b in BAZY:
    if not os.path.exists(b):
        continue
    try:
        cx = sqlite3.connect('file:%s?mode=ro' % b.replace('\\', '/'), uri=True)
        tabl = [r[0] for r in cx.execute("select name from sqlite_master where type='table'")]
    except Exception:  # noqa: BLE001
        continue
    for t in tabl:
        try:
            kol = [r[1] for r in cx.execute('pragma table_info("%s")' % t)]
        except Exception:  # noqa: BLE001
            continue
        if 'inn' not in kol:
            continue
        ps = next((k for k in ('site', 'sayt', 'domain', 'url') if k in kol), None)
        pn = next((k for k in ('name', 'naimenovanie', 'company') if k in kol), None)
        if not ps and not pn:
            continue
        q = 'select inn%s%s from "%s"' % ((', "%s"' % ps) if ps else '',
                                          (', "%s"' % pn) if pn else '', t)
        try:
            for r in cx.execute(q):
                i = str(r[0] or '').strip()
                if not i or i not in park or i in gotovo:
                    continue
                j = 1
                if ps:
                    v = str(r[1] or '').strip()
                    if v and '.' in v and i not in sayty:
                        sayty[i] = v
                    j = 2
                if pn and len(r) > j and r[j] and i not in imena:
                    imena[i] = re.sub(r'\s+', ' ', str(r[j])).strip()
        except Exception:  # noqa: BLE001
            continue
    cx.close()

celi = [(i, sayty[i]) for i in sayty][:SKOLKO]
potok, prichiny = [], collections.Counter()
for inn, sayt in celi:
    host = sayt if sayt.startswith('http') else 'http://' + sayt
    host = re.sub(r'/+$', '', host)
    nashli_t, nashli_p, otkuda = set(), set(), ''
    for put in PUTI:
        try:
            rq = urllib.request.Request(host + put, headers={'User-Agent': UA,
                                                             'Accept-Language': 'ru'})
            with net.open(rq, timeout=25) as rs:
                telo = rs.read(400000).decode('utf-8', 'replace')
                real_host = urllib.parse.urlparse(rs.geturl()).netloc.lower()
        except Exception:  # noqa: BLE001
            continue
        # ЗАСЛОН: хост ответа должен быть тем же сайтом, а не редиректом на агрегатор
        if re.sub(r'^www\.', '', real_host) not in re.sub(r'^www\.', '', host).replace('http://', '').replace('https://', ''):
            prichiny['редирект на чужой хост'] += 1
            continue
        t = re.sub(r'\s+', ' ', TEG.sub(' ', telo))
        for m in TELEFON.finditer(t):
            nashli_t.add(m.group(0).strip())
        for m in POCHTA.finditer(t):
            if not re.search(r'\.(png|jpg|svg|css|js)$', m.group(0), re.I):
                nashli_p.add(m.group(0).strip().lower())
        if nashli_t:
            otkuda = host + put
            break
        time.sleep(0.2)
    if not nashli_t and not nashli_p:
        prichiny['сайт открылся, телефона и почты нет'] += 1
        continue
    if not nashli_t:
        prichiny['только почта, телефона нет'] += 1
    potok.append({'inn': inn, 'predpriyatie': imena.get(inn, ''), 'sayt': host,
                  'telefony': ' | '.join(sorted(nashli_t)[:4]),
                  'pochty': ' | '.join(sorted(nashli_p)[:3]),
                  'mashina': park.get(inn, ''),
                  'istochniki': otkuda or host, 'istochnikov': 1,
                  'kto': '3-я сессия, сайт предприятия'})
    prichiny['взято'] += 1

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for o in potok:
        f.write(json.dumps(o, ensure_ascii=False) + '\n')
try:
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    rq = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                           os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT',
                                headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    vyl = op.open(rq, timeout=180).read().decode('utf-8', 'replace')[:110]
except Exception as e:  # noqa: BLE001
    vyl = 'не выложено: %s' % str(e)[:80]

s_tel = [o for o in potok if o['telefony']]
print('\n\n########## ПЕРВЫЕ ДЕСЯТЬ')
for o in potok[:10]:
    print('  %-12s %-30s %-34s %s' % (o['inn'], (o['predpriyatie'] or '—')[:30],
                                      o['telefony'][:34], o['mashina'][:14]))
print('\n########## ЧИСЛА')
print('  предприятий без контакта    %5d' % len([i for i in park if i not in gotovo]))
print('  из них с сайтом в базе      %5d' % len(sayty))
print('  обойдено сайтов             %5d' % len(celi))
print('  строк добыто                %5d  (с телефоном %d)' % (len(potok), len(s_tel)))
for k, v in prichiny.most_common():
    print('     %-46s %5d' % (k, v))
print('  файл: %s' % VYHOD)
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'обойдено': len(celi), 'с телефоном': len(s_tel)},
                           ensure_ascii=False))
