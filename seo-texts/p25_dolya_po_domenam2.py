# -*- coding: utf-8 -*-
"""Тот же жребий 555, но ОДНИМ прибором для всех доменов — браузером, а не urllib.

Прошлый замер сказал «доказано 31 %» и разложил вину по доменам так:

    etpgpb.ru      6 проб из 6 — 'ascii' codec can't encode
    zakupki.mos.ru 6 из 6 — каркас без машины
    zakupki.gov.ru 1 из 6 — первой стоит ссылка «как искали»

Я записала это в дефект ДАННЫХ и пошла чинить потоки. Починка вернула ноль исправленных
адресов по всем четырём файлам — а ноль, повторённый четыре раза, это диагноз прибора, а не
данных. Проверка показала: в потоках кириллицы нет вообще (ссылки ЭТП ГПБ уже в процентном
виде), «как искали» первой не стоит ни в одной строке базы. Значит все три обвинения были
не про данные, а про мерку:

  * `urllib` тянет ИСХОДНЫЙ html. ЭТП ГПБ, портал Москвы и Тендер.Про рисуют страницу
    скриптом, и в исходном html машины нет никогда — прибор обязан был врать в одну сторону;
  * «'ascii' codec» приходил не из потока, а из строк базы, собранной из ДРУГИХ каналов
    (реестр Ростехнадзора: `ural.gosnadzor.ru/…?поиск=…`, 209 ссылок, плюс `мосводосток.рф`);
  * порядок ссылок в базе уже верный: строк, где первой стоит поиск по слову, — 0.

Здесь мерка одна на все домены: серверный браузер, видимый текст страницы. И у неё есть
ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ — заведомо ложная ссылка, которая обязана дать «не доказывает».
Если контроль скажет «доказывает», числа не печатаются как истина: сломан прибор.

Разделяю два исхода, которые прошлый замер складывал в один:
    НЕ ДОКАЗАЛИ ДАННЫЕ  страница открылась, машины или предприятия на ней нет
    НЕ ПРОЧЁЛ ПРИБОР    страница не открылась, капча, пусто

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
NA_DOMEN = int(os.environ.get('P25_NA_DOMEN', '6'))
KRUPNYH = int(os.environ.get('P25_DOMENOV', '8'))
POTOKOV = int(os.environ.get('P25_POTOKOV', '3'))
MASH = re.compile(r'компрессор|воздуходув|нагнетател|ГПА|осушител|азот|кислород|ВРУ', re.I)
# Ложная ссылка контроля: карточка извещения с несуществующим реестровым номером.
KONTROL = ('https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html'
           '?regNumber=09999999999999999999999')


def prigodno(u):
    try:
        p = _up.urlsplit(u)
        host = p.netloc
        if re.search(r'[^\x00-\x7F]', host):
            host = host.encode('idna').decode('ascii')
        return _up.urlunsplit((p.scheme, host,
                               _up.quote(p.path, safe="/%:@&=+$,~!*'()"),
                               _up.quote(p.query, safe="/%:@&=+$,?~!*'()"), ''))
    except Exception:  # noqa: BLE001
        return u


def domen(u):
    return re.sub(r'^https?://(?:www\.)?([^/]+).*', r'\1', u).lower()


def vidimyy_tekst(u):
    """Видимый текст страницы серверным браузером. Пусто — значит прибор не прочёл."""
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
        return '', str(e)[:28]
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
        us = [prigodno(u) for u in str(o.get('istochniki') or '').split(' | ')
              if u.startswith('http')]
        if us and o.get('inn'):
            stroki.append((o, us))

po_domenu = collections.defaultdict(list)
for o, us in stroki:
    po_domenu[domen(us[0])].append((o, us[0]))
krupnye = [d for d, v in sorted(po_domenu.items(), key=lambda x: -len(x[1]))[:KRUPNYH]]
random.seed(555)
zadaniya = []
for d in krupnye:
    for o, u in random.sample(po_domenu[d], min(NA_DOMEN, len(po_domenu[d]))):
        zadaniya.append((d, o, u))

zamok = threading.Lock()
ochered = list(zadaniya)
itog = collections.defaultdict(collections.Counter)


def rabotnik():
    while True:
        with zamok:
            if not ochered:
                return
            d, o, u = ochered.pop()
        t, oshibka = vidimyy_tekst(u)
        if not t:
            with zamok:
                itog[d]['НЕ ПРОЧЁЛ ПРИБОР (%s)' % (oshibka or 'пусто')] += 1
            continue
        est_m = bool(MASH.search(t))
        est_p = o['inn'] in re.sub(r'\D', '', t)
        if not est_p and o.get('predpriyatie'):
            korni = [w for w in re.findall(r'[А-ЯЁA-Z]{7,}', o['predpriyatie'].upper())]
            est_p = bool(korni) and any(k in t.upper() for k in korni[:2])
        with zamok:
            itog[d]['ДОКАЗЫВАЕТ' if (est_m and est_p)
                    else ('ЧАСТИЧНО: машина есть, предприятия не видно' if est_m
                          else 'НЕ ДОКАЗАЛИ ДАННЫЕ: страница открылась, машины нет')] += 1


niti = [threading.Thread(target=rabotnik) for _ in range(POTOKOV)]
for n in niti:
    n.start()
kt, ko = vidimyy_tekst(KONTROL)
# Контроль прост: на карточке с несуществующим номером машины быть НЕ МОЖЕТ. Если прибор
# и там разглядел компрессор — он находит машину везде, и его «доказывает» ничего не стоит.
kontrol_ok = not MASH.search(kt or '')
kontrol_vidno = (kt or '')[:90]
for n in niti:
    n.join()

print('\n\n########## ПО ДОМЕНАМ, ОДИН ПРИБОР — БРАУЗЕР')
print('  %-24s %7s %6s %8s %9s' % ('домен', 'строк', 'проб', 'доказ.', 'частично'))
vd = vp = vdan = vpri = 0
for d in krupnye:
    sch = itog[d]
    prob = sum(sch.values())
    dok = sch['ДОКАЗЫВАЕТ']
    ne_dan = sum(v for k, v in sch.items() if k.startswith('НЕ ДОКАЗАЛИ'))
    ne_pri = sum(v for k, v in sch.items() if k.startswith('НЕ ПРОЧЁЛ'))
    vd += dok
    vp += prob
    vdan += ne_dan
    vpri += ne_pri
    print('  %-24s %7d %6d %8d %9d   данные %d / прибор %d'
          % (d[:24], len(po_domenu[d]), prob, dok,
             sum(v for k, v in sch.items() if k.startswith('ЧАСТИЧНО')), ne_dan, ne_pri))

print('\n########## ЧИСЛА')
print('  строк со ссылкой всего        %6d' % len(stroki))
print('  ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ        %s'
      % ('сказал «машины нет» на несуществующем извещении — прибор умеет говорить нет'
         if kontrol_ok else 'НАШЁЛ МАШИНУ НА НЕСУЩЕСТВУЮЩЕМ ИЗВЕЩЕНИИ — ПРИБОР СЛОМАН'))
print('  что контроль увидел           %s' % (kontrol_vidno or '(пусто)'))
print('  проверено ссылок              %6d' % vp)
print('  доказывают                    %6d  (%.0f%%)' % (vd, 100.0 * vd / max(1, vp)))
print('  не доказали ДАННЫЕ            %6d' % vdan)
print('  не прочёл ПРИБОР              %6d  (это не про качество данных)' % vpri)
if vp - vpri:
    print('  доля доказанных среди ПРОЧТЁННЫХ %.0f%%' % (100.0 * vd / (vp - vpri)))
print('ИТОГ ' + json.dumps({'проб': vp, 'доказывают': vd, 'не данные': vdan,
                            'не прибор': vpri, 'контроль': bool(kontrol_ok)},
                           ensure_ascii=False))
