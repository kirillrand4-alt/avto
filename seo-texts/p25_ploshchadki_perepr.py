# -*- coding: utf-8 -*-
"""РТС и Росэлторг: перепроверка. Прошлый заход дал 503 и 404 — оба про прибор, не про площадку.

РТС отвечал 503 на все восемь слов подряд, Росэлторг — 404 на все восемь. Восемь одинаковых
ответов подряд это не восемь фактов, а один: мой заход площадке не подходит. У Росэлторга
адрес я вообще сочинила, а рабочий лежит в нашем же сборщике площадок:

    https://www.roseltorg.ru/procedures/search?currency=all&query_field=<слово>

Плюс обе площадки режут датацентровые адреса, поэтому иду БРАУЗЕРОМ (и Росэлторг — через
дельфин-профиль, как записано в сборщике), а не простым запросом.

Заслон: если у разных слов вернётся одинаковый ответ — это снова диагноз прибора. Печатаю
длину текста и число найденных номеров процедур по каждому слову, чтобы одинаковость была
видна сразу.

Числа в КОНЦЕ.
"""
import collections
import json
import os
import re
import subprocess
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

DIR = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(DIR, 'server', 'run_on_server.py')
SLOVA = ['компрессор', 'винтовой компрессор', 'генератор азота', 'генератор кислорода',
         'воздуходувка', 'компрессорная станция']
TEG = re.compile(r'<[^>]+>')
PLOSH = {
    'РТС-тендер': dict(
        url=lambda q: 'https://www.rts-tender.ru/poisk?searchtext=' + urllib.parse.quote(q),
        dolphin=False),
    'Росэлторг': dict(
        url=lambda q: ('https://www.roseltorg.ru/procedures/search?currency=all&query_field='
                       + urllib.parse.quote(q)),
        dolphin=True),
}


def probe(url, dolphin):
    args = {'url': url, 'screenshot': False, 'return_html': True, 'html_cap': 900000,
            'wait_ms': 30000, 'proxy': False, 'ignore_https_errors': True}
    if dolphin:
        args['dolphin_profile'] = os.environ.get('DOLPHIN_PROFILE', '829115286')
        args['dolphin_keep'] = True
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


def rabota(par):
    imya, slovo = par
    p = PLOSH[imya]
    h, err = probe(p['url'](slovo), p['dolphin'])
    t = re.sub(r'\s+', ' ', TEG.sub(' ', h))
    nomera = set(re.findall(r'\b(\d{6,12})\b', t))
    est = slovo.split()[-1][:6].lower() in t.lower()
    return imya, slovo, len(t), len(nomera), est, err


zadaniya = [(i, s) for i in PLOSH for s in SLOVA]
rez = []
with ThreadPoolExecutor(max_workers=2) as ex:
    rez = list(ex.map(rabota, zadaniya))

print('\n\n########## ПО СЛОВАМ')
for imya, slovo, dl, nom, est, err in rez:
    print('  %-12s %-24s текст %6d знаков | номеров %4d | слово на странице %-5s %s'
          % (imya, slovo[:24], dl, nom, est, err))
svod = collections.defaultdict(list)
for imya, slovo, dl, nom, est, err in rez:
    svod[imya].append((dl, nom, est))
print('\n########## ЧИСЛА')
for imya, v in svod.items():
    dliny = {x[0] for x in v}
    print('  %-12s разных длин ответа %d из %d | слово найдено у %d | номеров всего %d'
          % (imya, len(dliny), len(v), sum(1 for x in v if x[2]), sum(x[1] for x in v)))
    if len(dliny) <= 1:
        print('     ЗАСЛОН: все ответы одинаковой длины — площадка отдаёт одно и то же')
print('ИТОГ ' + json.dumps({k: {'разных ответов': len({x[0] for x in v}),
                                'слово найдено': sum(1 for x in v if x[2])}
                            for k, v in svod.items()}, ensure_ascii=False))
