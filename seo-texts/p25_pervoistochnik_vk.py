# -*- coding: utf-8 -*-
"""Прочитать ПОЛНЫЙ первоисточник поста ВК — через API с токеном, а не через curl.

Панель показывает письмо #61: ИНН 5404476926, ООО ГК «СОДРУЖЕСТВО», Новосибирская
область, ОКВЭД 43.29 (строительно-монтажные работы). Повод: «Завод по глубокой
переработке сои в Белогорске выходит на проектную мощность».

Сайт, с которого взят адрес, я уже прочитала целиком: `sodrugestvo.ru/contacts` — это ГК
«Содружество», **Калининградская область, г. Светлый**, и `partners@sodrugestvo.ru` там
подписан как «Служба закупок материалов, оборудования и услуг». То есть адрес правильный,
а ИНН — от однофамильца из Новосибирска.

Осталась третья сцепка: НОВОСТЬ. Пост ВК простым запросом не читается — отдаёт заглушку
«Your browser is out of date», 245 знаков. Это ровно та ошибка, о которой предупреждал
владелец: снимок выдачи вместо первоисточника. Читаю пост через API с токеном сервера.

Токен нигде не печатаю — только длину и факт наличия. Только чтение.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, r'C:\sender\server')
POSTY = ['-99292882_44771', '-225065204_13785']

tok = ''
for imya in ('VK_TOKEN', 'VK_SERVICE_TOKEN', 'VK_ACCESS_TOKEN', 'VK_APP_TOKEN'):
    if os.environ.get(imya):
        tok = os.environ[imya]
        print('токен из окружения: %s, длина %d' % (imya, len(tok)))
        break
if not tok:
    for put in (r'C:\sender\_ops\vk_token.py', r'C:\sender\server\vk_token.py'):
        if os.path.exists(put):
            t = open(put, encoding='utf-8', errors='replace').read()
            m = re.search(r'["\']([a-f0-9]{60,})["\']', t)
            if m:
                tok = m.group(1)
                print('токен из файла %s, длина %d' % (put, len(tok)))
                break
if not tok:
    print('ИТОГ ' + json.dumps({'токена нет': True}, ensure_ascii=False))
    raise SystemExit

D = urllib.request.build_opener(urllib.request.ProxyHandler({}))
url = ('https://api.vk.com/method/wall.getById?posts=%s&extended=1&v=5.199'
       % urllib.parse.quote(','.join(POSTY)))
req = urllib.request.Request(url, headers={'Authorization': 'Bearer %s' % tok})
try:
    d = json.loads(D.open(req, timeout=40).read().decode('utf-8', 'replace'))
except Exception as e:  # noqa: BLE001
    print('запрос упал: %s' % str(e)[:200])
    raise SystemExit

if 'error' in d:
    print('ВК ответил ошибкой: %s' % str(d['error'])[:220])
    raise SystemExit

r = d.get('response') or {}
items = r.get('items') if isinstance(r, dict) else r
grupy = {g['id']: g.get('name', '') for g in (r.get('groups') or [])} if isinstance(r, dict) else {}

print('\n=== ПОСТОВ ПОЛУЧЕНО: %d' % len(items or []))
for it in (items or []):
    tekst = re.sub(r'\s+', ' ', str(it.get('text') or ''))
    ow = abs(int(it.get('owner_id') or 0))
    print('\n' + '=' * 66)
    print('пост -%s_%s   сообщество: %s' % (ow, it.get('id'), grupy.get(ow, '?')))
    print('знаков в тексте: %d' % len(tekst))
    print('НАЗВАНО ЛИ «Содружество»: %s' % bool(re.search(r'Содружеств', tekst, re.I)))
    print('Белогорск: %s | Амурская: %s | Калининград: %s | Новосибирск: %s'
          % (bool(re.search(r'Белогорск', tekst, re.I)),
             bool(re.search(r'Амурск|Приамур', tekst, re.I)),
             bool(re.search(r'Калининград', tekst, re.I)),
             bool(re.search(r'Новосибирск', tekst, re.I))))
    print('какие юрлица названы: %s'
          % re.findall(r'(?:ООО|АО|ПАО|ЗАО|ОАО|ГК)\s*[«"][^»"]{2,40}[»"]', tekst)[:6])
    print('ТЕКСТ ЦЕЛИКОМ:')
    print('  %s' % tekst[:2600])

print('\nИТОГ ' + json.dumps({'постов': len(items or [])}, ensure_ascii=False))
