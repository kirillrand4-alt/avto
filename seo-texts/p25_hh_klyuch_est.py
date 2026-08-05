# -*- coding: utf-8 -*-
"""Есть ли ключ hh на сервере — и что именно нужно `col_hh`, чтобы заработать.

Владелец: «hh мне выдал ключ разработчика». Значит дельфин-обход больше не нужен: с
токеном приложения `api.hh.ru` отвечает нормально, а это дешевле и быстрее браузера.

Ключ в репозиторий и в чат не тащим — правило владельца: секреты живут переменной
окружения на сервере. Поэтому прибор НЕ печатает значение: он печатает только ЕСТЬ или
НЕТ и длину. Показать секрет в выводе задания — то же самое, что закоммитить его.

ЧТО СМОТРЮ:
  1. переменные окружения сервера, похожие на hh-ключ;
  2. файлы `C:\\sender\\_ops` и `C:\\sender`, где обычно лежат токены (по имени, не по
     содержимому);
  3. что именно требует hh: у него ДВА обязательных условия, и про второе забывают —
     заголовок `HH-User-Agent` с названием приложения и почтой, иначе 403 даже с токеном.

И сразу проверяю на живом запросе: без токена и (если найдётся) с токеном — печатаю коды
ответов. Это и будет доказательство, что путь чинится ключом, а не переписыванием.
"""
import json
import os
import re
import urllib.request

IMENA = ('HH_TOKEN', 'HH_API_TOKEN', 'HH_APP_TOKEN', 'HH_CLIENT_SECRET', 'HH_KEY',
         'HHTOKEN', 'HH_ACCESS_TOKEN', 'HH_USER_AGENT', 'HH_CLIENT_ID')

print('=== 1. ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ (печатаю только наличие и длину)')
nashli = {}
for k, v in os.environ.items():
    if 'HH' in k.upper() and len(k) <= 24:
        nashli[k] = len(v or '')
        print('  %-22s есть, длина %d' % (k, len(v or '')))
for k in IMENA:
    if k not in nashli:
        print('  %-22s НЕТ' % k)

print('\n=== 2. ФАЙЛЫ С ПОХОЖИМИ ИМЕНАМИ (только имена, содержимое не печатаю)')
for d in (r'C:\sender\_ops', r'C:\sender', r'C:\sender\server'):
    if not os.path.isdir(d):
        continue
    for n in sorted(os.listdir(d)):
        if re.search(r'hh|token|key|secret|\.env$', n, re.I) and not n.endswith('.py'):
            p = os.path.join(d, n)
            try:
                sz = os.path.getsize(p)
            except Exception:  # noqa: BLE001
                sz = -1
            print('  %-52s %d байт' % (p, sz))

print('\n=== 3. ЖИВАЯ ПРОВЕРКА api.hh.ru')
Q = ('https://api.hh.ru/vacancies?text=%22%D0%BC%D0%B0%D1%88%D0%B8%D0%BD%D0%B8%D1%81%D1'
     '%82+%D0%BA%D0%BE%D0%BC%D0%BF%D1%80%D0%B5%D1%81%D1%81%D0%BE%D1%80%D0%BD%D1%8B%D1%85'
     '+%D1%83%D1%81%D1%82%D0%B0%D0%BD%D0%BE%D0%B2%D0%BE%D0%BA%22&per_page=3&area=113')


def probuem(zag, opisanie):
    try:
        r = urllib.request.urlopen(urllib.request.Request(Q, headers=zag), timeout=25)
        d = json.loads(r.read().decode('utf-8', 'replace'))
        n = len(d.get('items') or [])
        print('  %-46s код %s, вакансий %d, всего найдено %s'
              % (opisanie, r.getcode(), n, d.get('found')))
        for v in (d.get('items') or [])[:3]:
            print('      · %s — %s (%s)'
                  % (str((v.get('employer') or {}).get('name'))[:40],
                     str(v.get('name'))[:50],
                     str((v.get('area') or {}).get('name'))[:20]))
        return True
    except Exception as e:  # noqa: BLE001
        print('  %-46s %s: %s' % (opisanie, type(e).__name__, str(e)[:120]))
        return False


probuem({'Accept': 'application/json'}, 'без заголовков (как сейчас в col_hh)')
probuem({'Accept': 'application/json',
         'HH-User-Agent': 'RuspromLeads/1.0 (info@rusprom.example)'},
        'только HH-User-Agent, без токена')
tok = ''
for k in IMENA:
    if os.environ.get(k):
        tok = os.environ[k]
        break
if tok:
    probuem({'Accept': 'application/json', 'Authorization': 'Bearer ' + tok,
             'HH-User-Agent': 'RuspromLeads/1.0 (info@rusprom.example)'},
            'с токеном из окружения + HH-User-Agent')
else:
    print('  %-46s токена в окружении нет — проверить нечем' % 'с токеном')

print('\nИТОГ ' + json.dumps({'переменные с HH': sorted(nashli),
                              'токен найден': bool(tok)}, ensure_ascii=False))
