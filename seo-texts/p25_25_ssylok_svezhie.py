# -*- coding: utf-8 -*-
"""ДВАДЦАТЬ ПЯТЬ СЛУЧАЙНЫХ ССЫЛОК-ДОКАЗАТЕЛЬСТВ, свежим жребием и глазами.

Правило владельца: в конце проверить глазами, куда ведут хотя бы 25 случайных ссылок. Прежняя
такая проверка шла по старому жребию (seed 825) и по файлам из `/home/user/work`, которых
больше нет. Здесь — по ЖИВОЙ базе и живому парку, новым жребием, и с СОХРАНЁННЫМ снимком
каждой страницы: снимок кладётся на дроп, чтобы смотреть глазами, а не верить моему пересказу.

Что проверяется у каждой ссылки — то, ради чего она в строке стоит:

    ссылка машины    на отрисованной странице стоит слово нашей машины
    ссылка контакта  на странице стоит ИМЕННО ТОТ номер (последние 10 цифр) или почта
    ссылка ИНН       цифры ИНН стоят СРАЗУ ПОСЛЕ слова «ИНН» (не «где-то в тексте»:
                     ЕИС находит выдуманный ИНН по чужому ОГРН — проверено снимком)

Исходы РАЗДЕЛЕНЫ, потому что смысл у них разный:
    ДОКАЗЫВАЕТ                  — искомое на странице есть
    ОТКРЫЛАСЬ, ИСКОМОГО НЕТ     — потеря, её надо назвать
    НЕ ОТКРЫЛАСЬ                — состояние прибора или сайта, НЕ улика против факта

ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: к выборке подмешивается ссылка того же вида с подменённым хвостом
(несуществующий номер). Если мерка объявит её доказывающей — числам верить нельзя.

ПУТЬ: мимо прокси (он отвечает 407) и без проверки сертификата, иначе браузер не открывает
даже example.com и все 25 строк стали бы «не открылась».

Числа в КОНЦЕ.
"""
import collections
import csv
import io
import json
import os
import random
import re
import subprocess
import sys
import threading
import urllib.request

DIR = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(DIR, 'server', 'run_on_server.py')
SCRATCH = os.environ.get('P25_SCRATCH', '.')
BAZA = os.path.join(SCRATCH, 'PARK-BAZA-EDINAYA-3S.csv')
PARK = ['park_ingest_3.jsonl', 'park_ingest_3b.jsonl', 'park_ingest_3c.jsonl',
        'park_ingest_3d.jsonl']
VYHOD = os.path.join(SCRATCH, 'PARK-25-SSYLOK-GLAZAMI-3S.jsonl')
SKOLKO = int(os.environ.get('P25_SKOLKO', '25'))
ZHREBIY = int(os.environ.get('P25_ZHREBIY', '100826'))
POTOKOV = int(os.environ.get('P25_POTOKOV', '3'))
MASH = re.compile(r'компрессор|воздуходув|нагнетател|осушител|азотн|кислородн|'
                  r'воздухоразделит|ГПА', re.I)
INN_POSLE = re.compile(r'ИНН[^0-9A-Za-zА-Яа-я]{0,8}(\d{10}|\d{12})')
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def des(t):
    c = re.sub(r'\D', '', str(t or ''))
    return c[-10:] if len(c) >= 10 else ''


kandidaty = []
# 1) ссылки из единой базы: у контакта — своя, у машины — своя
if os.path.exists(BAZA):
    with io.open(BAZA, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f, delimiter=';'):
            inn = (r.get('inn') or '').strip()
            for u in str(r.get('istochniki') or '').split(' | '):
                if u.startswith('http') and (r.get('nomer') or r.get('pochta')):
                    kandidaty.append({'url': u, 'vid': 'контакт', 'inn': inn,
                                      'iskat': des(r.get('nomer')) or (r.get('pochta') or ''),
                                      'imya': (r.get('predpriyatie') or '')[:80],
                                      'chelovek': (r.get('chelovek') or '')[:60]})
            for u in str(r.get('mashina_ssylka') or '').split(' | '):
                if u.startswith('http'):
                    kandidaty.append({'url': u, 'vid': 'машина', 'inn': inn, 'iskat': '',
                                      'imya': (r.get('predpriyatie') or '')[:80],
                                      'chelovek': ''})
# 2) ссылки из парка: доказательство машины и доказательство ИНН
for f in PARK:
    put = os.path.join(SCRATCH, f)
    if not os.path.exists(put):
        continue
    for s in io.open(put, encoding='utf-8'):
        try:
            o = json.loads(s)
        except Exception:  # noqa: BLE001
            continue
        for u in str(o.get('istochniki') or '').split(' | '):
            if u.startswith('http'):
                kandidaty.append({'url': u, 'vid': 'машина', 'inn': str(o.get('inn') or ''),
                                  'iskat': '', 'imya': str(o.get('organizaciya')
                                                           or o.get('zakazchik') or '')[:80],
                                  'chelovek': ''})
        if str(o.get('ssylka_inn') or '').startswith('http'):
            kandidaty.append({'url': o['ssylka_inn'], 'vid': 'ИНН',
                              'inn': str(o.get('inn') or ''), 'iskat': '',
                              'imya': str(o.get('organizaciya') or '')[:80], 'chelovek': ''})

random.seed(ZHREBIY)
random.shuffle(kandidaty)
vybor = kandidaty[:SKOLKO]
# ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: та же форма ссылки, но с несуществующим хвостом
kontrol = None
if vybor:
    obr = dict(vybor[0])
    obr['url'] = re.sub(r'(\d{6,})', lambda m: m.group(1)[:-4] + '0000', obr['url'])
    if obr['url'] == vybor[0]['url']:
        obr['url'] = obr['url'].rstrip('/') + '/999999999'
    obr['vid'] = 'КОНТРОЛЬ (' + obr['vid'] + ')'
    kontrol = obr

zamok = threading.Lock()
ochered = list(vybor) + ([kontrol] if kontrol else [])
gotovo, sch = [], collections.Counter()


def brauzer(u, imya_snimka):
    zadanie = {'url': u, 'wait_ms': 16000, 'proxy': False, 'ignore_https_errors': True,
               'screenshot': True, 'screenshot_drop': True, 'inn': imya_snimka,
               'eval_js': {'return': 'document.body ? document.body.innerText : ""'}}
    try:
        p = subprocess.run([sys.executable, RUNNER, 'browser_probe',
                            json.dumps(zadanie, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=600)
    except Exception as e:  # noqa: BLE001
        return '', str(e)[:50], ''
    syr = p.stdout or ''
    i = syr.find('{')
    if i < 0:
        return '', (p.stderr or syr)[:50], ''
    try:
        d = json.loads(syr[i:syr.rfind('}') + 1]).get('data') or {}
    except Exception:  # noqa: BLE001
        return '', syr[:50], ''
    return (re.sub(r'\s+', ' ', str(d.get('eval_js_value') or '')),
            (d.get('error') or '')[:50], d.get('screenshot_drop') or '')


def sudit(z, t):
    """Есть ли на странице ТО, ради чего ссылка стоит."""
    if z['vid'].startswith('КОНТРОЛЬ'):
        vid = z['vid'][z['vid'].find('(') + 1:-1]
    else:
        vid = z['vid']
    if vid == 'машина':
        return bool(MASH.search(t)), 'слово машины на странице'
    if vid == 'ИНН':
        return z['inn'] in INN_POSLE.findall(t), 'ИНН сразу после слова «ИНН»'
    isk = z.get('iskat') or ''
    if not isk:
        return bool(MASH.search(t)), 'слово машины на странице'
    if '@' in isk:
        return isk.lower() in t.lower(), 'почта на странице'
    return isk in re.sub(r'\D', '', t), 'последние 10 цифр номера на странице'


def rabotnik():
    while True:
        with zamok:
            if not ochered:
                return
            z = dict(ochered.pop())
            nomer = len(gotovo) + 1
        imya = 'GLAZA-%02d-%s' % (nomer, (z['inn'] or 'bez')[:12])
        t, osh, snimok = brauzer(z['url'], imya)
        if not t or len(t) < 120:
            ishod, chem = 'НЕ ОТКРЫЛАСЬ', osh or 'текста нет'
        else:
            est, chem = sudit(z, t)
            ishod = 'ДОКАЗЫВАЕТ' if est else 'ОТКРЫЛАСЬ, ИСКОМОГО НЕТ'
        with zamok:
            sch['%s | %s' % (z['vid'], ishod)] += 1
            gotovo.append(dict(z, ishod=ishod, chem=chem, snimok=snimok,
                               dlina_teksta=len(t), oshibka=osh,
                               kusok=t[:200]))


niti = [threading.Thread(target=rabotnik) for _ in range(POTOKOV)]
for n in niti:
    n.start()
for n in niti:
    n.join()

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for z in gotovo:
        f.write(json.dumps(z, ensure_ascii=False) + '\n')
try:
    rq = urllib.request.Request('%s/%s' % (drop, os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT', headers=tok)
    vyl = op.open(rq, timeout=180).read().decode('utf-8', 'replace')[:70]
except Exception as e:  # noqa: BLE001
    vyl = 'НЕ ВЫЛОЖЕНО: %s' % str(e)[:50]

print('\n\n########## ПО ОДНОЙ')
for z in gotovo:
    print('  %-24s %-22s %s' % (z['vid'][:24], z['ishod'][:22], z['url'][:78]))
    print('        %-42s снимок %s' % (('ищем: ' + (z['chem'] or ''))[:42],
                                       z['snimok'] or '—'))

nast = [z for z in gotovo if not z['vid'].startswith('КОНТРОЛЬ')]
kont = [z for z in gotovo if z['vid'].startswith('КОНТРОЛЬ')]
print('\n########## ЧИСЛА')
print('  ссылок в котле        %d' % len(kandidaty))
print('  проверено             %d' % len(nast))
for k, v in sch.most_common():
    print('     %-50s %4d' % (k[:50], v))
dok = len([z for z in nast if z['ishod'] == 'ДОКАЗЫВАЕТ'])
otkr = len([z for z in nast if z['ishod'] != 'НЕ ОТКРЫЛАСЬ'])
print('  ДОКАЗЫВАЮТ %d из %d проверенных; из ОТКРЫВШИХСЯ %d из %d'
      % (dok, len(nast), dok, otkr))
print('  ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: %s'
      % ('; '.join('%s -> %s' % (z['url'][-40:], z['ishod']) for z in kont) or 'не построен'))
print('  контроль %s' % ('ЧИСТ' if all(z['ishod'] != 'ДОКАЗЫВАЕТ' for z in kont)
                         else 'ПРОБИТ — числам верить нельзя'))
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'проверено': len(nast), 'доказывают': dok,
                            'открылись': otkr,
                            'контроль чист': all(z['ishod'] != 'ДОКАЗЫВАЕТ' for z in kont)},
                           ensure_ascii=False))
