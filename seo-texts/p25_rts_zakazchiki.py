# -*- coding: utf-8 -*-
"""РТС-тендер как источник ИНН. Канал был закрыт МОИМ прибором, а не площадкой.

История числа. В сводке стояло «РТС — 503», и это читалось как «площадка закрыта». Проверка
с сервера показала другое: код ответа правда 503, но **страница рисуется** — 19 189 знаков
видимого текста, слово «компрессор» встречается 28 раз, в разметке 35 длинных номеров. То
есть сборщик верил коду ответа и не смотрел на содержимое. Ноль был диагнозом прибора.

Дальше я сняла с ЖИВОГО фронта, как устроена выдача, и это оказалось подарком:

    /poisk/id/<номер>/                     карточка процедуры — первоисточник
    /poisk/organizator/<ИНН>-<КПП>/        организатор, И ИНН СТОИТ ПРЯМО В АДРЕСЕ
    /poisk/comorganizers/<ИНН>-<КПП>/      то же для коммерческих

Значит ИНН не надо вытаскивать из карточки и сшивать по названию — он лежит в ссылке, а
рядом текстом стоит имя организации. Это самый дешёвый ИНН из всех моих каналов.

ЗАСЛОНЫ, повторены по опыту ЕИС:
  1. слово машины обязано стоять в НАЗВАНИИ процедуры, а не где-то на странице: иначе в
     парк приедет «поставка канцтоваров» с соседнего блока выдачи;
  2. уполномоченные органы и агентства госзаказа машиной не владеют — вон, с причиной
     (в первой же выдаче попалось «МИНИСТЕРСТВО … ПО РЕГУЛИРОВАНИЮ КОНТРАКТНОЙ СИСТЕМЫ»);
  3. у строки обязана быть ссылка-первоисточник — карточка процедуры.

ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ: одним из слов идёт выдуманное «щварцкопфер». Если по нему придут
строки — выдача не фильтрует по слову, и всем остальным числам грош цена.

Числа в КОНЦЕ.
"""
import collections
import io
import json
import os
import re
import subprocess
import sys
import threading
import urllib.parse
import urllib.request

DIR = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(DIR, 'server', 'run_on_server.py')
SCRATCH = os.environ.get('P25_SCRATCH', '.')
VYHOD = os.path.join(SCRATCH, 'PARK-RTS-PODTV-3S.jsonl')
SLOVA = [w for w in os.environ.get(
    'P25_SLOVA',
    'компрессор|компрессорная станция|воздуходувка|азотная станция|генератор кислорода|'
    'турбокомпрессор|щварцкопфер').split('|') if w.strip()]
STRANIC = int(os.environ.get('P25_STRANIC', '4'))
POTOKOV = int(os.environ.get('P25_POTOKOV', '3'))
MASH = re.compile(r'компрессор|воздуходув|нагнетател|осушител|азотн|кислородн|'
                  r'воздухоразделит|ГПА', re.I)
POSREDNIK = re.compile(r'по регулированию контрактной|агентств\w+ (государственн|муниципальн)|'
                       r'департамент\w* (государственн|муниципальн)|комитет\w* .{0,30}закупк|'
                       r'управлени\w* .{0,30}закупк|центр\w* .{0,20}закупок|'
                       r'уполномоченн\w+ орган', re.I)
drop = os.environ.get('DROP_URL', '').rstrip('/')
tok = {'X-Drop-Token': os.environ.get('DROP_TOKEN', '')}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# Разбор выдачи делаю НА САМОЙ СТРАНИЦЕ: у каждой карточки процедуры поднимаюсь к общему
# предку, который держит и ссылку организатора, и заголовок. Пара «карточка + организатор»
# собирается браузером, а не догадкой по расстоянию в тексте.
JS = ("(function(){var out=[];"
      "document.querySelectorAll('a[href^=\"/poisk/id/\"]').forEach(function(a){"
      "var u=a; for(var i=0;i<6&&u;i++){"
      "var org=u.querySelector&&u.querySelector('a[href*=\"/poisk/organizator/\"],"
      "a[href*=\"/poisk/comorganizers/\"]');"
      "if(org){out.push({karta:a.getAttribute('href'),org:org.getAttribute('href'),"
      "imya:(org.innerText||'').trim().slice(0,160),"
      "tekst:(u.innerText||'').replace(/\\s+/g,' ').trim().slice(0,400)});break;}"
      "u=u.parentElement;}});"
      "var vid={};var res=[];out.forEach(function(o){if(!vid[o.karta+o.org]){vid[o.karta+o.org]=1;"
      "res.push(o);}});return JSON.stringify(res);})()")


def stranica(slovo, n):
    u = ('https://www.rts-tender.ru/poisk/search?keywords=%s&Page=%d'
         % (urllib.parse.quote(slovo), n))
    args = {'url': u, 'screenshot': False, 'return_html': False, 'wait_ms': 18000,
            'proxy': False, 'ignore_https_errors': True,
            'eval_js': {'return': JS, 'after_ms': 1500}}
    try:
        p = subprocess.run([sys.executable, RUNNER, 'browser_probe',
                            json.dumps(args, ensure_ascii=False)],
                           capture_output=True, timeout=420)
        s = p.stdout.decode('utf-8', 'replace')
        d = json.loads(s[s.find('{'):]).get('data') or {}
        return u, json.loads(d.get('eval_js_value') or '[]')
    except Exception as e:  # noqa: BLE001
        return u, [{'oshibka': str(e)[:40]}]


zamok = threading.Lock()
zadaniya = [(w, n) for w in SLOVA for n in range(1, STRANIC + 1)]
gotovo, sch, po_slovu = {}, collections.Counter(), collections.Counter()


def rabotnik():
    while True:
        with zamok:
            if not zadaniya:
                return
            slovo, n = zadaniya.pop()
        u, bloki = stranica(slovo, n)
        for b in bloki:
            if b.get('oshibka'):
                with zamok:
                    sch['страница не открылась: %s' % b['oshibka'][:24]] += 1
                continue
            m = re.search(r'/poisk/(?:organizator|comorganizers)/(\d{10,12})-', b.get('org') or '')
            if not m:
                with zamok:
                    sch['в ссылке организатора нет ИНН'] += 1
                continue
            inn = m.group(1)
            tekst = b.get('tekst') or ''
            if not MASH.search(tekst):
                with zamok:
                    sch['в названии процедуры нет нашей машины'] += 1
                continue
            if POSREDNIK.search(b.get('imya') or ''):
                with zamok:
                    sch['уполномоченный орган — машиной не владеет'] += 1
                continue
            karta = 'https://www.rts-tender.ru' + (b.get('karta') or '')
            with zamok:
                z = gotovo.get((inn, karta))
                if not z:
                    gotovo[(inn, karta)] = {
                        'inn': inn, 'predpriyatie': (b.get('imya') or '')[:160],
                        'predmet': tekst[:300], 'istochniki': karta,
                        'kak_iskali': u, 'slovo': slovo, 'istochnikov': 1,
                        'kto': '3-я сессия, РТС-тендер по словам'}
                    sch['принято'] += 1
                    po_slovu[slovo] += 1


niti = [threading.Thread(target=rabotnik) for _ in range(POTOKOV)]
for n in niti:
    n.start()
for n in niti:
    n.join()

with io.open(VYHOD, 'w', encoding='utf-8') as f:
    for z in gotovo.values():
        f.write(json.dumps(z, ensure_ascii=False) + '\n')
try:
    rq = urllib.request.Request('%s/%s' % (drop, os.path.basename(VYHOD)),
                                data=io.open(VYHOD, 'rb').read(), method='PUT', headers=tok)
    vyl = op.open(rq, timeout=300).read().decode('utf-8', 'replace')[:70]
except Exception as e:  # noqa: BLE001
    vyl = 'НЕ ВЫЛОЖЕНО: %s' % str(e)[:50]

print('\n\n########## ПЕРВЫЕ ДЕСЯТЬ')
for z in list(gotovo.values())[:10]:
    print('  %-12s %-40s %s' % (z['inn'], z['predpriyatie'][:40], z['predmet'][:60]))
print('\n########## ЧИСЛА')
print('  слов                            %5d (страниц на слово %d)' % (len(SLOVA), STRANIC))
print('  строк принято                   %5d  (предприятий %d)'
      % (len(gotovo), len({z['inn'] for z in gotovo.values()})))
print('  --- по слову')
for k, v in po_slovu.most_common():
    print('     %-34s %5d' % (k[:34], v))
kontrol = po_slovu.get('щварцкопфер', 0)
print('  ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ «щварцкопфер»: %s'
      % ('строк 0 — выдача правда фильтрует по слову' if not kontrol
         else 'ПРИШЛО %d СТРОК — выдача НЕ фильтрует, числам верить нельзя' % kontrol))
print('  --- что снято и почему')
for k, v in sch.most_common():
    print('     %-46s %5d' % (k[:46], v))
print('  файл: %s' % VYHOD)
print('  выложено: %s' % vyl)
print('ИТОГ ' + json.dumps({'строк': len(gotovo),
                            'предприятий': len({z['inn'] for z in gotovo.values()}),
                            'контроль': kontrol}, ensure_ascii=False))
