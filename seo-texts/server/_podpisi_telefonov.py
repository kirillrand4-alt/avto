# -*- coding: utf-8 -*-
r"""Инпласт: как номера записаны у нас и что стоит рядом с ними на странице.

На сайте у каждого номера подписана роль — «Комм. отдел», «Бухгалтерия»,
«Руководство». В паспорте сайта телефонов нет вовсе (промпт их не спрашивает),
в phone_contacts роль пустая. Значит, подпись надо брать оттуда же, откуда сам
номер, — из страницы в кэше обхода. Здесь проверяем, что это работает.
"""
import gzip
import json
import re
import sqlite3

ИНН = '6143038853'
КЕШ = r'C:\seostat\drop\pagecache\%s.json.gz' % ИНН
d = {}
e = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
e.row_factory = sqlite3.Row
r = e.execute("select coalesce(phones,'') p, coalesce(site,'') s from companies "
              'where inn=?', (ИНН,)).fetchone()
d['companies.phones'] = dict(r) if r else {}
d['phone_contacts'] = [dict(x) for x in e.execute(
    'select * from phone_contacts where inn=?', (ИНН,))]
d['people'] = [dict(x) for x in e.execute('select * from people where inn=?', (ИНН,))]
e.close()

_ТЕЛ = re.compile(r'(?:\+7|8)?[\s\-()]{0,3}\d[\d\s\-()]{8,20}\d')


def _цифры(т):
    return ''.join(c for c in str(т or '') if c.isdigit())


найдено = {}
try:
    with gzip.open(КЕШ, 'rb') as f:
        кэш = json.loads(f.read().decode('utf-8', 'replace'))
except Exception as ex:  # noqa: BLE001
    кэш = {}
    d['кэш'] = str(ex)[:100]
d['страниц_в_кэше'] = len(кэш.get('pages') or [])
for стр in (кэш.get('pages') or [])[:60]:
    текст = re.sub(r'<[^>]+>', '\n', стр.get('html') or '')
    текст = re.sub(r'&nbsp;', ' ', текст)
    for m in _ТЕЛ.finditer(текст):
        ц = _цифры(m.group(0))
        if len(ц) < 10:
            continue
        ключ = ц[-10:]
        перед = текст[max(0, m.start() - 70):m.start()]
        куски = [x.strip(' \t\r\n·-—:;|') for x in re.split(r'[\n;|]+', перед)]
        подпись = next((x for x in reversed(куски) if 2 < len(x) <= 40), '')
        узел = найдено.setdefault(ключ, {'как_на_странице': m.group(0).strip(),
                                         'подписи': [], 'страницы': []})
        if подпись and подпись not in узел['подписи']:
            узел['подписи'].append(подпись)
        if стр.get('url') and стр['url'] not in узел['страницы']:
            узел['страницы'].append(стр['url'])
d['номера_со_страниц'] = найдено
print(json.dumps(d, ensure_ascii=False, indent=1)[:4200])
