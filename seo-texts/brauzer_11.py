# -*- coding: utf-8 -*-
"""Обход одиннадцати доменов браузером НА СЕРВЕРЕ.

Из песочницы это делать нельзя: замер показал, что из 11 доменов, которые серверу
открылись, песочнице доступны ТРИ — mmk.ru, toaz.ru и площадки gazprom-neft не резолвятся
вовсе, а кириллические домены ломают запрос ещё на кодировке. Сервер их видит, значит и
обходить должен он.

Берём не главную, а страницы, где живут люди: контакты, руководство, структура.
"""
import json, subprocess, sys, time

RUN = '/home/user/avto/seo-texts/server/run_on_server.py'
DROP = '/home/user/avto/seo-texts/server/drop_client.sh'
PUTI = ['', '/contacts', '/kontakty', '/about/contacts', '/rukovodstvo',
        '/about/management', '/company/management']
d = json.load(open('molchat-proverka.json', encoding='utf-8'))
domeny = [x['domen'] for x in d if 'ОТКРЫЛСЯ' in x['itog']]
out, snimki = [], []
for i, dom in enumerate(domeny, 1):
    vzyato = 0
    for put in PUTI:
        arg = json.dumps({'url': f'https://{dom}{put}', 'wait': 4}, ensure_ascii=False)
        try:
            p = subprocess.run([sys.executable, RUN, 'browser_probe', arg],
                               capture_output=True, text=True, timeout=300)
            o = json.loads(p.stdout[p.stdout.find('{'):])
        except Exception:  # noqa: BLE001
            continue
        dd = o.get('data') or {}
        if dd.get('screenshot_drop'):
            snimki.append(dd['screenshot_drop'])
        t = (dd.get('text_snippet') or '')
        if len(t) < 200:
            continue
        vzyato += 1
        out.append({'domen': dom, 'stranica': f'https://{dom}{put}',
                    'zagolovok': dd.get('title') or '', 'tekst': t})
    print(f'[{i}/{len(domeny)}] {dom}: страниц с текстом {vzyato}', file=sys.stderr, flush=True)
json.dump(out, open('brauzer-11.json', 'w', encoding='utf-8'), ensure_ascii=False)
print(f'страниц собрано {len(out)} с {len(domeny)} доменов', file=sys.stderr)
for s in snimki:
    subprocess.run(['bash', DROP, 'del', s], capture_output=True, timeout=60)
print(f'снимков браузера удалено с дропа: {len(snimki)}', file=sys.stderr)
