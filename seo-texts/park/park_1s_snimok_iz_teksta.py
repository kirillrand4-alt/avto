# -*- coding: utf-8 -*-
"""Снимок-доказательство там, где браузеру страницу не отдают, а обычной загрузке — отдают.

Откуда взялось. Владелец открыл `NOMER-7718560636-9022000976.png` и написал: «пустой
скриншот». Разбор дал 12 пустых кадров из 99, и 11 из них — с Тендер.Про. Причина не в
съёмщике: **Тендер.Про не отдаёт страницу браузеру с сервера** — приходит пустой каркас, и
снимать нечего. Из песочницы та же страница обычной загрузкой приходит целиком, с номером и
фамилией; но браузеру в песочнице наружу не дают вовсе (ERR_CONNECTION_RESET при трёх разных
настройках прокси, тогда как curl тот же адрес открывает).

То есть ни в одном из двух мест нет пары «браузер + доступ». Поэтому снимок делается из того,
что доступно: страница берётся загрузкой, её HTML отрисовывается в браузере локально
(`set_content`), там же подсвечивается номер и ставится плашка.

Что этот снимок доказывает и чего НЕ доказывает — написано на самом снимке, чтобы его нельзя
было прочесть неправильно:

    доказывает      — что по такому-то адресу в такой-то день лежал текст, где номер стоит
                      рядом с фамилией и должностью; виден сам кусок текста и адрес;
    НЕ доказывает   — как страница выглядит в браузере: оформление сайта не подгружалось,
                      кадр показывает текст страницы, а не её вид.

Проверки те же три, что и у обычного съёмщика (`park_1s_snimok_nomera.py`), и это важно:
номер связно, фамилия рядом, страница связана с предприятием. Снимок без них не делается.

Запуск: python3 park_1s_snimok_iz_teksta.py <откуда> <сколько>
"""
import html as _html
import json
import os
import re
import sys
import time
import urllib.request

D = os.path.dirname(os.path.abspath(__file__))
ZAD = os.environ.get('NOMERA_ZAD', os.path.join(D, '_zad_pesochnica.json'))
VYHOD = os.environ.get('NOMERA_VYHOD', os.path.join(D, 'park_nomera_iz_teksta.jsonl'))
SNIMKI = os.environ.get('NOMERA_SNIMKI', os.path.join(D, 'snimki_pesochnica'))
EXE = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
OTKUDA = int(sys.argv[1]) if len(sys.argv) > 1 else 0
SKOLKO = int(sys.argv[2]) if len(sys.argv) > 2 else 40
PUSTOY_KADR = 12000
AGREGATORY = ('prodoctorov', 'vk.com', 'ok.ru', 'facebook', 'instagram', 'avito', 'youla',
              'hh.ru', 'superjob', 'zoon.', 'yell.', '2gis', 'flamp', 'orgpage', 'rusprofile',
              'list-org', 'checko', 'careerist', 'vseinstrumenti')
PLOSHCHADKI = ('zakupki.gov.ru', 'etpgpb.ru', 'tender.pro', 'roseltorg.ru', 'fabrikant.ru',
               'rts-tender.ru', 'tektorg.ru', 'sberbank-ast.ru', 'zakupki.mos.ru',
               'gosnadzor.ru', 'monitor-pb.ru', 'docs.cntd.ru')


def tekst_stranicy(url):
    """HTML и его текст. Загрузка обычная — та, которой эти адреса отдаются."""
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9'})
    with urllib.request.urlopen(req, timeout=60) as r:
        syro = r.read(3000000)
    h = syro.decode('utf-8', 'replace')
    bez = re.sub(r'<(script|style|noscript)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
    t = _html.unescape(re.sub(r'<[^>]+>', ' ', bez))
    return h, re.sub(r'[ \s]+', ' ', t)


def svyazno(cifry, tekst):
    return re.search(r'[\s\-()+]{0,3}'.join(cifry), tekst)


def familiya_ryadom(chelovek, tekst, poz):
    slova = re.findall(r'[А-ЯЁ][а-яё]{2,}', chelovek or '')
    okno = tekst[max(0, poz - 260):poz + 260]
    for w in slova:
        if w in okno:
            return True, w
    return False, (slova[0] if slova else '')


def svyaz_s_predpriyatiem(url, tekst):
    domen = re.sub(r'^https?://(www\.)?([^/]+).*', r'\2', url or '').lower()
    if any(a in domen for a in AGREGATORY):
        return False, 'агрегатор: имя есть, принадлежность не доказана'
    if any(pl in domen for pl in PLOSHCHADKI):
        return True, 'площадка закупок: карточку заводит сам заказчик'
    return True, 'сайт источника: ' + domen


def stranica_dlya_snimka(z, tekst, m, kakoe, chem):
    """Своя разметка: плашка с оговоркой, цитата в контексте, подсвеченный номер."""
    nachalo = max(0, m.start() - 900)
    kusok = tekst[nachalo:m.start() + 900]
    podsvet = _html.escape(kusok).replace(
        _html.escape(m.group(0)),
        '<mark style="background:#ffe600;outline:2px solid #d40000">%s</mark>'
        % _html.escape(m.group(0)))
    for w in [x for x in re.findall(r'[А-ЯЁ][а-яё]{2,}', z.get('chelovek') or '') if x]:
        podsvet = podsvet.replace(_html.escape(w),
                                  '<mark style="background:#c8ffc8">%s</mark>' % _html.escape(w))
    return """<!doctype html><meta charset="utf-8">
<body style="margin:0;font:15px/1.6 Arial,sans-serif;color:#111;background:#fff">
<div style="border:3px solid #d40000;padding:14px 18px;margin:0 0 12px 0">
  <b style="font-size:17px">Доказательство личного номера</b><br>
  <span style="color:#555">кто:</span> <b>%s</b>%s<br>
  <span style="color:#555">номер:</span> <b style="background:#ffe600">%s</b><br>
  <span style="color:#555">адрес:</span> %s<br>
  <span style="color:#555">снято:</span> %s · фамилия рядом с номером: <b>%s</b> · %s
</div>
<div style="background:#fff8d8;border:1px solid #d9c86a;padding:9px 14px;margin:0 0 12px 0;
            font-size:13px;color:#5a4a00">
  Кадр показывает ТЕКСТ страницы, полученный по этому адресу, а не её вид в браузере:
  оформление сайта не подгружалось. Сайт не отдаёт страницу браузеру с нашего сервера,
  поэтому текст взят обычной загрузкой и отрисован здесь без изменений.
</div>
<div style="white-space:pre-wrap;border:1px solid #ccc;padding:14px 18px">%s</div>
</body>""" % (_html.escape(z.get('chelovek') or ''),
              (' — ' + _html.escape(z['dolzhnost'])) if z.get('dolzhnost') else '',
              _html.escape(m.group(0)), _html.escape(z['ssylka']),
              time.strftime('%Y-%m-%d'), _html.escape(kakoe), _html.escape(chem), podsvet)


zad = json.load(open(ZAD, encoding='utf-8'))[OTKUDA:OTKUDA + SKOLKO]
os.makedirs(SNIMKI, exist_ok=True)
from playwright.sync_api import sync_playwright

itog = []
with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True, executable_path=EXE, args=['--no-sandbox'])
    pg = br.new_context(viewport={'width': 1600, 'height': 1100}).new_page()
    for z in zad:
        r = {k: z.get(k) for k in ('inn', 'chelovek', 'dolzhnost', 'nomer', 'ssylka')}
        cifry = re.sub(r'\D', '', z['nomer'])[-10:]
        try:
            _, tekst = tekst_stranicy(z['ssylka'])
            r['znakov'] = len(tekst)
            m = svyazno(cifry, tekst)
            if not m:
                golyy = re.sub(r'\D', '', tekst)
                r['vyvod'] = ('СКЛЕЙКА соседних чисел, не телефон' if cifry in golyy
                              else 'номера на странице нет')
            else:
                est, kakoe = familiya_ryadom(z.get('chelovek'), tekst, m.start())
                svyaz, chem = svyaz_s_predpriyatiem(z['ssylka'], tekst)
                r['familiya_ryadom'], r['svyaz'] = est, chem
                r['citata'] = tekst[max(0, m.start() - 170):m.start() + 90]
                if not est:
                    r['vyvod'] = 'номер есть, но фамилии рядом нет — ЧЕЙ НЕ ЯСНО'
                elif not svyaz:
                    r['vyvod'] = 'номер и фамилия есть, но страница не связана с предприятием'
                else:
                    imya = 'NOMER-%s-%s.png' % (z['inn'], cifry)
                    put = os.path.join(SNIMKI, imya)
                    pg.set_content(stranica_dlya_snimka(z, tekst, m, kakoe, chem),
                                   wait_until='load')
                    pg.wait_for_timeout(250)
                    pg.screenshot(path=put, full_page=False)
                    bayt = os.path.getsize(put)
                    r['snimok'], r['bayt_snimka'] = imya, bayt
                    r['snimok_pustoy'] = 1 if bayt < PUSTOY_KADR else 0
                    r['vyvod'] = ('ДОКАЗАНО: номер и фамилия на снимке' if bayt >= PUSTOY_KADR
                                  else 'снимок пустой (%d б)' % bayt)
        except Exception as e:  # noqa: BLE001
            r['vyvod'] = 'страницу не дали: ' + str(e)[:70]
        itog.append(r)
        with open(VYHOD, 'a', encoding='utf-8') as f:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
    br.close()

from collections import Counter
print('обработано: %d (с %d)' % (len(itog), OTKUDA))
for v, n in Counter((x.get('vyvod') or '')[:46] for x in itog).most_common():
    print('  %-48s %d' % (v, n))
print('журнал: %s' % VYHOD)
