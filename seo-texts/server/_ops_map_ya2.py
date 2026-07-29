# -*- coding: utf-8 -*-
"""Шаг: карточка знаний Яндекса отдала РОВНО ОДИН телефон. А на самой карточке
Я.Карт их больше? Открываем живую страницу организации и смотрим СЫРОЙ текст.

Порядок на каждую компанию: статикой (дёшево) -> если пусто/капча, рендер
дельфином с решателем капч. Текст снимаем EC._текст (убирает script/style),
телефоны — EC.phones_in. Ничего не пишем в базу.
"""
import json
import re
import sys
import traceback
import urllib.request

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import browser_probe as BP    # noqa: E402

# id профилей Я.Карт, добытые предыдущим замером (mapurl из knowledge_graph)
ЦЕЛИ = [
    ('ЛОРП', '1103001599'),
    ('ГалоПолимер Пермь', '1727422811'),
    ('Западная ГРК', '143115011957'),
]
ПОДПИСЬ = ('отдел', 'приемн', 'приёмн', 'снабж', 'сбыт', 'закуп', 'секретар',
           'диспетчер', 'бухгалт', 'кадр', 'главный', 'служба', 'факс')


def P(*a):
    print(*a)
    sys.stdout.flush()


def статикой(u):
    try:
        r = EC._DIRECT.open(urllib.request.Request(
            u, headers={'User-Agent': getattr(EC.VC, 'UA', 'Mozilla/5.0')}), timeout=25)
        raw = r.read()
        return EC._раскодировать(raw, r.headers.get('Content-Type', '')), r.status
    except Exception as ex:  # noqa: BLE001
        тело = ''
        try:
            тело = EC._раскодировать(ex.read()[:3000], '')
        except Exception:  # noqa: BLE001
            pass
        return тело, f'ОШ {type(ex).__name__} {str(ex)[:50]}'


def разбор(метка, html):
    чист = EC._текст(html)
    тел = sorted({re.sub(r'[\s\-()\u2012-\u2015]', '', m.group(0))
                  for m in EC.phones_in(чист)})
    P(f'    [{метка}] html={len(html)} чистый_текст={len(чист)} телефонов={len(тел)} {тел[:6]}')
    низ = чист.lower()
    P(f'    [{метка}] капча={("captcha" in низ or "робот" in низ)} '
      f'кириллицы={len(re.findall(chr(1072) + "-" + chr(1103), низ))}')
    for сл in ПОДПИСЬ:
        for m in list(re.finditer(сл, чист, re.I))[:1]:
            P(f'      [{сл}] …{чист[max(0, m.start() - 80):m.start() + 90]}…')
    return тел, чист


def main():
    ток = EC._read_secret('DOLPHIN_TOKEN')
    проф = [x for x in re.split(r'[,\s]+', EC._HH_DOLPHIN_DEF) if x]
    P('дельфин профили:', проф, 'токен:', bool(ток))
    итог = {'целей': len(ЦЕЛИ), 'статика_ок': 0, 'браузер_ок': 0, 'тел_макс': 0}
    for i, (имя, pid) in enumerate(ЦЕЛИ):
        u = f'https://yandex.ru/profile/{pid}'
        P(f'=== {имя} {u}')
        html, st = статикой(u)
        P('    статика:', st, 'байт', len(html))
        тел, чист = разбор('статика', html)
        if тел:
            итог['статика_ок'] += 1
        if len(тел) < 2:
            арг = {'url': u, 'return_html': True, 'html_cap': 900000,
                   'wait_ms': 9000, 'screenshot': False, 'solve': True}
            if ток and проф:
                арг['dolphin_profile'] = проф[i % len(проф)]
                арг['dolphin_token'] = ток
            try:
                r = BP.probe(арг)
            except Exception as ex:  # noqa: BLE001
                r = {'error': f'{type(ex).__name__}: {str(ex)[:80]}'}
            h = (r or {}).get('html') or ''
            P('    браузер: err', str((r or {}).get('error'))[:70])
            тел2, _ = разбор('браузер', h)
            if тел2:
                итог['браузер_ок'] += 1
            тел = тел2 if len(тел2) > len(тел) else тел
        итог['тел_макс'] = max(итог['тел_макс'], len(тел))
    P('ИТОГ ЯКАРТЫ-СТРАНИЦА: ' + json.dumps(итог, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        P('!! упало:', traceback.format_exc()[-700:].replace('\n', ' | '))
