# -*- coding: utf-8 -*-
"""34 ссылки из 48 показали МАШИНУ и не показали ПРЕДПРИЯТИЕ. Разбираю, чья это вина.

Замер одним прибором (браузер, жребий 555) дал неожиданное: прибор прочёл все 48 страниц,
машина видна на 47, а «доказывает» вышло только 13. Разница целиком в одном вопросе —
названо ли на странице ПРЕДПРИЯТИЕ. Ответ решает, что чинить:

    если предприятие на странице ЕСТЬ, а я его не узнаю   -> плоха моя мерка имени;
    если предприятия на странице НЕТ вовсе                -> ссылка доказывает машину,
                                                             но не её владельца, и это
                                                             дефект самого доказательства.

Смешивать эти два случая нельзя: первый чинится строкой кода, второй — пересбором ссылок.

Здесь по каждой пробе печатается: название из потока, найден ли ИНН, найден ли корень имени
и — главное — КУСОК видимого текста вокруг слова «заказчик», чтобы глазами увидеть, чьё имя
там на самом деле стоит.

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
import threading
import urllib.parse as _up

DIR = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(DIR, 'server', 'run_on_server.py')
SCRATCH = os.environ.get('P25_SCRATCH', '.')
POTOKI = ['park_ingest_3.jsonl', 'park_ingest_3b.jsonl', 'park_ingest_3c.jsonl',
          'park_ingest_3d.jsonl']
NA_DOMEN = int(os.environ.get('P25_NA_DOMEN', '3'))
KRUPNYH = int(os.environ.get('P25_DOMENOV', '6'))
POTOKOV = int(os.environ.get('P25_POTOKOV', '3'))
MASH = re.compile(r'компрессор|воздуходув|нагнетател|ГПА|осушител|азот|кислород|ВРУ', re.I)
MUSOR = re.compile(r'^(ООО|ОАО|ПАО|АО|ЗАО|ФГУП|ГУП|МУП|НАО|ИП|ФКУ|ФГБУ|ГБУ|МБУ|УК|НПО|НПП|'
                   r'ПК|СПК|КФХ)$', re.I)


def kodirovat(u):
    m = re.match(r'^https?://(?:www\.)?tender\.pro/(?:#/)?tender/(\d+)', u or '')
    if m:
        u = 'https://www.tender.pro/api/tender/%s/view_public' % m.group(1)
    try:
        p = _up.urlsplit(u)
        host = p.netloc
        if re.search(r'[^\x00-\x7F]', host):
            host = host.encode('idna').decode('ascii')
        return _up.urlunsplit((p.scheme, host,
                               _up.quote(p.path, safe="/%:@&=+$,~!*'()"),
                               _up.quote(p.query, safe="/%:@&=+$,?~!*'()"),
                               _up.quote(p.fragment, safe="/%:@&=+$,?~!*'()")))
    except Exception:  # noqa: BLE001
        return u


def slova_imeni(imya):
    """Слова названия без организационной формы и без кавычек. Мерка имени должна ловить
    «ЮГК» — у прежней порог был семь букв, и такие имена она не видела в принципе."""
    return [w for w in re.findall(r'[А-ЯЁA-Z]{3,}', (imya or '').upper()) if not MUSOR.match(w)]


def vidimyy(u):
    args = {'url': u, 'screenshot': False, 'return_html': False, 'wait_ms': 14000,
            'proxy': False, 'ignore_https_errors': True,
            'eval_js': {'return': 'document.body ? document.body.innerText : ""',
                        'after_ms': 300}}
    try:
        p = subprocess.run([sys.executable, RUNNER, 'browser_probe',
                            json.dumps(args, ensure_ascii=False)],
                           capture_output=True, timeout=400)
        s = p.stdout.decode('utf-8', 'replace')
        d = json.loads(s[s.find('{'):]).get('data') or {}
    except Exception as e:  # noqa: BLE001
        return '', str(e)[:30]
    return re.sub(r'\s+', ' ', str(d.get('eval_js_value') or '')), ''


stroki = []
for f in POTOKI:
    put = os.path.join(SCRATCH, f)
    if not os.path.exists(put):
        continue
    for s in io.open(put, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        us = [kodirovat(u) for u in str(o.get('istochniki') or '').split(' | ')
              if u.startswith('http')]
        if us and o.get('inn'):
            stroki.append((o, us[0]))

po_domenu = collections.defaultdict(list)
for o, u in stroki:
    po_domenu[re.sub(r'^https?://(?:www\.)?([^/]+).*', r'\1', u).lower()].append((o, u))
krupnye = [d for d, v in sorted(po_domenu.items(), key=lambda x: -len(x[1]))[:KRUPNYH]]
random.seed(555)
zadaniya = []
for d in krupnye:
    for o, u in random.sample(po_domenu[d], min(NA_DOMEN, len(po_domenu[d]))):
        zadaniya.append((d, o, u))

zamok = threading.Lock()
ochered = list(zadaniya)
sch = collections.Counter()
razbor = []


def rabotnik():
    while True:
        with zamok:
            if not ochered:
                return
            d, o, u = ochered.pop()
        t, err = vidimyy(u)
        if not t:
            with zamok:
                sch['страница не прочлась'] += 1
            continue
        cif = re.sub(r'\D', '', t)
        est_inn = o['inn'] in cif
        sl = slova_imeni(o.get('predpriyatie') or '')
        popal = [w for w in sl if w in t.upper()]
        # где на странице стоит слово «заказчик» и что написано сразу после него
        m = re.search(r'(заказчик\w*|организатор\w*)\s*[:\-—]?\s*(.{0,90})', t, re.I)
        vokrug = m.group(0)[:110] if m else '(слова «заказчик» на странице нет)'
        with zamok:
            if est_inn:
                sch['ИНН напечатан на странице'] += 1
            elif popal:
                sch['ИНН нет, но имя предприятия найдено словами'] += 1
            else:
                sch['ни ИНН, ни слов названия — предприятие не названо'] += 1
            if len(razbor) < 24:
                razbor.append((d, o['inn'], (o.get('predpriyatie') or '')[:34],
                               'ИНН' if est_inn else ('слова: %s' % ','.join(popal[:3])
                                                      if popal else 'НЕТ'),
                               'машина' if MASH.search(t) else 'машины нет', vokrug))


niti = [threading.Thread(target=rabotnik) for _ in range(POTOKOV)]
for n in niti:
    n.start()
for n in niti:
    n.join()

print('\n\n########## ПО ОДНОЙ ПРОБЕ')
for d, inn, imya, kak, mash, vokrug in razbor:
    print('  %-16s %-11s %-34s %-16s %s' % (d[:16], inn, imya, kak, mash))
    print('        рядом с «заказчик»: %s' % vokrug)
print('\n########## ЧИСЛА')
for k, v in sch.most_common():
    print('  %-52s %5d' % (k[:52], v))
print('ИТОГ ' + json.dumps(dict(sch), ensure_ascii=False))
