# -*- coding: utf-8 -*-
"""Источник номера: «сайт компании» – только если домен совпал с сайтом компании.

Доводка к istochniki_i_kommentarii.py. Первая версия называла сайтом компании любой
незнакомый домен без пометки «сторонний». Замер (probe_sayt): сайт есть у 64 из 65
компаний, у 72 из 80 номеров домен источника совпал с ним, остальные – площадки (3) и
чужие сайты (5, все уже помечены разборщиком). Значит правило можно сделать строгим:
  * Tender.pro, ЕИС и другие площадки, агрегаторы – по домену, как было;
  * домен совпал с company.sayt (или поддомен; кириллический домен сравнивается
    в punycode) – «сайт компании»;
  * не совпал или разборщик пометил «сторонний» – «сторонний сайт» + «уточнить, чей номер»;
  * сайта у компании нет и пометки нет – нейтрально «сайт · домен», без утверждения.
Плюс «Источники проверки компании»: у Meyer там 80 строк «ЛПР: …» – это те же номера,
подпись у них теперь такая же.
"""
import io
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
APP = os.path.join(KOREN, 'app')
WEB = os.path.join(APP, 'web.py')
C = os.path.join(APP, 'templates', 'centro.html')
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
DROP = r'C:\seostat\drop\drop-storage'
PORT = 8016
PUT = '/obzvon-meyer'
BEKAP = os.path.join(KOREN, '_bekap', time.strftime('istochniki-sayt-%Y%m%d-%H%M%S'))

NOVYY = r'''def _domen(url) -> str:
    """Домен без www и порта; кириллический – в punycode, чтобы «йуми.рф» в ссылке и
    «xn--h1abj1a.xn--p1ai» в карточке считались одним сайтом. Схема необязательна:
    у компаний сайт часто записан как «kras-oil.ru»."""
    u = str(url or "").strip().lower()
    if not u:
        return ""
    if "//" in u:
        u = u.split("//", 1)[1]
    d = u.split("/", 1)[0].split("?", 1)[0].split(":", 1)[0].strip(".")
    d = d[4:] if d.startswith("www.") else d
    if any(ord(ch) > 127 for ch in d):
        try:
            d = d.encode("idna").decode("ascii")
        except UnicodeError:
            pass
    return d if "." in d else ""


def _domen_pokaz(url) -> str:
    """Домен для подписи – как в ссылке (кириллица остаётся кириллицей)."""
    u = str(url or "").strip()
    if "//" in u:
        u = u.split("//", 1)[1]
    d = u.split("/", 1)[0].split("?", 1)[0].split(":", 1)[0].lower()
    return d[4:] if d.startswith("www.") else d


def _vid_istochnika(url, source="", sayt="") -> dict:
    """URL источника номера -> {"podpis": «тендерная площадка Tender.pro», "vid", "domen",
    "zametki": [(текст, важно)]}. sayt – сайт компании из карточки: «сайт компании»
    говорится, только если домен с ним совпал. Пустой URL -> podpis ""."""
    s = str(source or "").lower()
    zametki = []
    if "через сотрудника" in s:
        zametki.append(("выход на ЛПР через сотрудника", False))
    if "не удалось сверить" in s:
        zametki.append(("не сверен со страницей", True))
    if not str(url or "").strip().lower().startswith("http"):
        return {"podpis": "", "vid": "", "domen": "", "zametki": zametki}
    d, pokaz = _domen(url), _domen_pokaz(url)
    if not d:
        return {"podpis": "", "vid": "", "domen": "", "zametki": zametki}
    for kor, (vid, imya) in _TENDER_PLOSHCHADKI.items():
        if d == kor or d.endswith("." + kor):
            return {"podpis": "%s %s" % (vid, imya), "vid": vid, "domen": pokaz, "zametki": zametki}
    if any(a in d for a in _AGREGATORY_VYPISOK):
        return {"podpis": "агрегатор выписок · %s" % pokaz, "vid": "агрегатор", "domen": pokaz,
                "zametki": zametki}
    dk = _domen(sayt)
    if dk and (d == dk or d.endswith("." + dk) or dk.endswith("." + d)):
        return {"podpis": "сайт компании · %s" % pokaz, "vid": "сайт компании", "domen": pokaz,
                "zametki": zametki}
    if dk or "стороннего сайта" in s:
        zametki.append(("не сайт компании – уточнить, чей номер", True))
        return {"podpis": "сторонний сайт · %s" % pokaz, "vid": "сторонний сайт", "domen": pokaz,
                "zametki": zametki}
    return {"podpis": "сайт · %s" % pokaz, "vid": "сайт", "domen": pokaz, "zametki": zametki}


templates.env.filters["vid_istochnika"] = _vid_istochnika
'''

if '--proverka' in sys.argv:
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    from collections import Counter
    from app.api import routes_centro_sales as rcs
    from app.obzvon import create_app
    from app import web
    from fastapi.testclient import TestClient

    plohih = 0

    def proverit(u, t):
        global plohih
        if not u:
            plohih += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))

    v = web._vid_istochnika
    for url, src, sayt, nado in (
            ('https://www.tender.pro/x', '', 'okmarket.ru', 'тендерная площадка Tender.pro'),
            ('https://zakupki.gov.ru/epz/1', '', 'elevatorn.ru', 'госзакупки ЕИС'),
            ('http://kras-oil.ru/', 'подпись со страницы', 'kras-oil.ru', 'сайт компании · kras-oil.ru'),
            ('https://shop.kras-oil.ru/k', '', 'https://www.kras-oil.ru/', 'сайт компании · shop.kras-oil.ru'),
            ('https://йуми.рф/kontakty', '', 'xn--h1abj1a.xn--p1ai', 'сайт компании · йуми.рф'),
            ('https://fortuna-agrohpp.ru/c', 'проверить: контакт со стороннего сайта', 'mrz.ru', 'сторонний сайт · fortuna-agrohpp.ru'),
            ('https://other.ru/c', '', 'mrz.ru', 'сторонний сайт · other.ru'),
            ('https://kras-oil.ru.evil.com/', '', 'kras-oil.ru', 'сторонний сайт · kras-oil.ru.evil.com'),
            ('https://shkxp.ru/k', 'контакт со стороннего сайта (shkxp.ru)', '', 'сторонний сайт · shkxp.ru'),
            ('https://some.ru/k', 'подпись со страницы', '', 'сайт · some.ru'),
            ('', 'подпись со страницы', 'kras-oil.ru', '')):
        p = v(url, src, sayt)['podpis']
        proverit(p == nado, 'вид %-34s сайт %-22s -> %r' % (url[:34], sayt[:22], p))
    proverit(web._domen('йуми.рф') == web._domen('https://xn--h1abj1a.xn--p1ai/'), 'кириллица = punycode: %s' % web._domen('йуми.рф'))

    k = sqlite3.connect(KAT)
    sayt = dict(k.execute('select inn, sayt from company'))
    for tabl in ('contact', 'person'):
        c = Counter(v(u, s, sayt.get(i))['vid'] or '(без ссылки)' for i, u, s in k.execute(
            'select inn, source_url, source from "%s"' % tabl))
        print('      %s по видам: %s' % (tabl, dict(c.most_common())))
        proverit(c.get('сайт компании') == {'contact': 72, 'person': 24}[tabl],
                 '%s: «сайт компании» = числу совпавших доменов в замере' % tabl)

    vnutr = next(z for z in vars(create_app()).values()
                 if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    vnutr.dependency_overrides[rcs.current_user] = lambda: {
        'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    with TestClient(vnutr) as kl:
        for inn in ('7826087713', '2441000946', '3524015320', '5636002901',
                    k.execute("select inn from contact where source like 'подпись со страницы%' limit 1").fetchone()[0]):
            o = kl.get(PUT + '/centro?inn=' + inn)
            t = o.text
            ssylki = re.findall(r'<div class="source-line"[^>]*>.*?</div>', t, re.S)
            vidno = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s)).strip() for s in ssylki]
            starye = [x for x in vidno if 'подпись со страницы' in x or 'сверено' in x or 'витрина' in x]
            proverit(o.status_code == 200 and not starye,
                     'карточка %s: %d строк источника, со строкой разборщика %d' % (inn, len(vidno), len(starye)))
            print('         ' + ' || '.join(sorted(set(vidno)))[:400])
            io.open(os.path.join(DROP, 'centro2-karta-istochnik-%s.html' % inn), 'w', encoding='utf-8').write(t)
    print()
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
    raise SystemExit(0)

os.makedirs(BEKAP, exist_ok=True)
log = []
t = io.open(WEB, encoding='utf-8').read()
m = re.search(r'def _domen\(url\) -> str:.*?templates\.env\.filters\["vid_istochnika"\] = _vid_istochnika\n', t, re.S)
if 'def _domen_pokaz' in t:
    log.append('[уже] web.py: сравнение с сайтом компании')
elif m:
    shutil.copy2(WEB, os.path.join(BEKAP, 'web.py'))
    io.open(WEB, 'w', encoding='utf-8').write(t[:m.start()] + NOVYY + t[m.end():])
    log.append('[ок] web.py: сравнение с сайтом компании')
else:
    log.append('[ЯКОРЬ] web.py – не правлю')
    print(log)
    raise SystemExit(1)

t = io.open(C, encoding='utf-8').read()
shutil.copy2(C, os.path.join(BEKAP, 'centro.html'))
zam = [
    ("{% set в = url|vid_istochnika(source) %}",
     "{% set _сайт = ((company.sayt or company.website or '') if company else '')|string %}\n"
     "  {% set в = url|vid_istochnika(source, _сайт) %}", 'макрос: сайт компании в разбор'),
    ("{{ (а|vid_istochnika(source)).podpis }}", "{{ (а|vid_istochnika(source, _сайт)).podpis }}", 'макрос: ссылки'),
    ("{{ source_link(item.source, item.source_url) }}</li>{% endfor %}</ul>",
     "{{ source_link(item.source, item.source_url, telefon=(item.field_name or '').startswith('ЛПР')) }}</li>{% endfor %}</ul>",
     'источники проверки компании: строки «ЛПР» как номера'),
]
for staro, novo, imya in zam:
    if novo in t:
        log.append('[уже] ' + imya)
    elif t.count(staro) == 1:
        t = t.replace(staro, novo, 1)
        log.append('[ок] ' + imya)
    else:
        log.append('[ЯКОРЬ: %d] %s' % (t.count(staro), imya))
io.open(C, 'w', encoding='utf-8').write(t)
for x in log:
    print('   ' + x)
if any('ЯКОРЬ' in x for x in log):
    raise SystemExit(1)

sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
for l in p.stdout.decode('cp866', 'replace').splitlines():
    if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
        subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
time.sleep(2)
lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
lg.write('\n===== перезапуск: источник номера по сайту компании %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
lg.flush()
subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg,
                 stderr=subprocess.STDOUT, creationflags=0x00000008 | 0x00000200,
                 close_fds=True, env=sreda)
time.sleep(10)
r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka'], capture_output=True,
                   timeout=900, cwd=KOREN, env=sreda)
print()
print('===== ПРОВЕРКА =====')
sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
if r.returncode:
    sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-3000:])
