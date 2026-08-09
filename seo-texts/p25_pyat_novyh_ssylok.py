# -*- coding: utf-8 -*-
"""Пять НОВЫХ случайных ссылок-доказательств — открыть и посмотреть, куда они ведут.

Прямое требование владельца: «в конце необходимо глазами проверить куда ведёт хотя бы 25
рандомных ссылок доказательства, ответить на вопрос — это всё откуда реально было достать
факты или контакты? если не всё, то доделать».

Беру ссылки из ОБОИХ своих потоков, а не из одного: `park_ingest_3.jsonl` доказывает
машину, `PARK-KONTAKTY-3S.jsonl` доказывает контакт. Проверять только машины значило бы
ответить на половину вопроса.

Что считается ответом по каждой ссылке — три исхода, и середина здесь важнее краёв:

    ДОКАЗЫВАЕТ            страница открылась И на ней есть то, ради чего ссылка стоит
                          (обозначение машины для потока парка, цифры номера для контакта)
    ОТКРЫЛАСЬ, НО ПУСТО   страница живая, а доказательства на ней нет — это либо
                          одностраничное приложение, которое рисует содержимое скриптом,
                          либо ссылка на раздел вместо документа. Пометка честная: канал
                          рабочий, прибор не тот.
    НЕ ОТКРЫЛАСЬ          код ответа или ошибка сети — печатаю как есть, без толкования

Про запятую в счёте: страница, которая открылась и НЕ доказала, — это не «битая ссылка».
Прошлый раз именно это различение показало, что Портал поставщиков Москвы отдаёт 200 и
пустое тело, потому что карточка приходит отдельным запросом, и «доказательства нет»
означало «страница ещё не отрисована».

Ссылки открываю С СЕРВЕРА: у песочницы другой выход в сеть, и «не открылась» из песочницы
ничего не сказало бы про то, доступен ли документ оттуда, где работает сбор.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import random
import re
import ssl
import urllib.request

POTOKI = [(r'C:\sender\_ops\park_ingest_3.jsonl', 'машина'),
          (r'C:\sender\_ops\PARK-KONTAKTY-3S.jsonl', 'контакт')]
SKOLKO = 5
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/120.0.0.0 Safari/537.36')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
net = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                  urllib.request.ProxyHandler({}))
TEG = re.compile(r'<[^>]+>')


def klyuch(s):
    return re.sub(r'[\s\-]', '', s or '').upper().replace(',', '.')


stroki = []
for put, chto in POTOKI:
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

random.seed(5150)
vybor = random.sample(stroki, min(SKOLKO, len(stroki)))
itogi, po_domenu, po_ishodu = [], collections.Counter(), collections.Counter()
for z in vybor:
    dom = re.sub(r'^https?://([^/]+).*', r'\1', z['url'])
    po_domenu[dom] += 1
    try:
        rq = urllib.request.Request(z['url'], headers={'User-Agent': UA,
                                                       'Accept-Language': 'ru'})
        with net.open(rq, timeout=60) as rs:
            kod = rs.getcode()
            telo = rs.read(500000).decode('utf-8', 'replace')
        text = re.sub(r'\s+', ' ', TEG.sub(' ', telo))
        est = False
        if z['chto'] == 'машина':
            est = any(klyuch(n) in klyuch(text) for n in z['iskat'].split(' | ') if len(n) > 3)
        else:
            cifry = re.sub(r'\D', '', z['iskat'])
            est = bool(cifry) and (cifry in re.sub(r'\D', '', text)
                                   or (z['iskat'] and '@' in z['iskat']
                                       and z['iskat'].lower() in text.lower()))
            if not est and z['imya']:
                fam = z['imya'].split(' ')[0]
                est = len(fam) > 3 and fam in text
        ishod = ('ДОКАЗЫВАЕТ' if est else
                 ('ОТКРЫЛАСЬ, НО ИСКОМОГО НЕТ (%d знаков текста)' % len(text)))
    except Exception as e:  # noqa: BLE001
        kod, ishod = 0, 'НЕ ОТКРЫЛАСЬ: %s' % str(e)[:60]
    po_ishodu[ishod.split(',')[0].split(':')[0]] += 1
    itogi.append((z['chto'], dom, kod, ishod, z['inn'], z['iskat'][:26], z['url']))

print('\n\n########## ДВАДЦАТЬ ПЯТЬ ССЫЛОК, ПО ОДНОЙ')
for chto, dom, kod, ishod, inn, isk, u in itogi:
    print('  [%s] %-26s http %-4s %-12s искали «%s»' % (chto, dom[:26], kod, inn, isk))
    print('        %s' % ishod)
    print('        %s' % u[:150])
print('\n########## ЧИСЛА')
print('  ссылок в потоках всего      %6d' % len(stroki))
print('  проверено                   %6d' % len(itogi))
for k, v in po_ishodu.most_common():
    print('     %-46s %4d' % (k[:46], v))
print('  --- по домену')
for k, v in po_domenu.most_common(10):
    print('     %-40s %4d' % (k[:40], v))
print('ИТОГ ' + json.dumps({'проверено': len(itogi),
                            'доказывают': po_ishodu.get('ДОКАЗЫВАЕТ', 0),
                            'открылись без искомого': po_ishodu.get('ОТКРЫЛАСЬ', 0),
                            'не открылись': po_ishodu.get('НЕ ОТКРЫЛАСЬ', 0)},
                           ensure_ascii=False))
