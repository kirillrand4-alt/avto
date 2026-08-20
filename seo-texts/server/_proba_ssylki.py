# -*- coding: utf-8 -*-
r"""Проба ссылки на лид: создаём, открываем как посторонний, проверяем срез.

Главное здесь — не «страница открылась», а ЧТО на ней. Проверяем, что наружу
не ушли ни адреса почты, ни подпись, с которой письмо было отправлено, и что
отозванная ссылка перестаёт работать.
"""
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.request

sys.path.insert(0, r'C:\sender')
sys.path.insert(0, r'C:\sender\sender')
import lid_ssylka as LS  # noqa: E402

БАЗА = 'http://127.0.0.1:8091'
итог = {}

c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
лид = c.execute(
    "select l.id, l.email, l.company_name, l.inn from leads l "
    "where l.status<>'deleted' and exists(select 1 from events e "
    "  where e.recipient_id=l.recipient_id and e.event_type like 'reply%') "
    'order by l.id desc limit 1').fetchone()
c.close()
if not лид:
    print(json.dumps({'нет подходящего лида': True}, ensure_ascii=False))
    raise SystemExit

итог['лид'] = {'id': лид['id'], 'компания': лид['company_name'],
               'адрес': лид['email'], 'инн': лид['inn']}
r = LS.sozdat(int(лид['id']), kto='проба')
итог['ссылка'] = r['url']


def взять(путь):
    try:
        o = urllib.request.urlopen(БАЗА + путь, timeout=25)
        return o.status, o.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        return 'ошибка', str(e)[:120]


код, стр = взять('/lid/%s' % r['token'])
итог['код'] = код
итог['знаков'] = len(стр)
if код == 200:
    адреса = set(re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', стр))
    итог['ПРОВЕРКА'] = {
        'адресов_на_странице': sorted(адреса)[:5],
        'адрес_лида_виден': bool(лид['email'] and лид['email'].lower() in стр.lower()),
        'подпись_видна': 'С уважением' in стр,
        'наш_ящик_виден': bool(re.search(
            r'kompressor-|compressor-|sort-systems|optic-sort|zernosort', стр)),
        'компания_видна': bool(лид['company_name']
                               and лид['company_name'][:12] in стр),
        'есть_переписка': 'Переписка' in стр,
        'есть_кому_звонить': 'Кому звонить' in стр,
        'не_индексировать': 'noindex' in стр,
    }
    итог['кусок'] = re.sub(r'<[^>]+>', ' ', стр)[:400]

# отзыв
LS.otozvat(int(лид['id']))
код2, _ = взять('/lid/%s' % r['token'])
итог['после_отзыва_код'] = код2
print(json.dumps(итог, ensure_ascii=False, indent=1)[:3000])
