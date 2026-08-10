# -*- coding: utf-8 -*-
"""СБОР checko через пул socks5 — исполняется на проверочном VPS, где пул достижим.

ЗАЧЕМ. Обогащение стояло: предприятий с доказанной машиной 2 146, контакт есть у 235.
Из контейнера сессии checko отдаёт 429 на ЛЮБОЙ путь (лимит на IP), а пул socks недостижим —
исходящий TCP на :3001 виснет. С VPS оба ограничения снимаются.

ФОРМА АДРЕСА ВЗЯТА ИЗ ГОТОВОГО `srv-checko_contacts.py`, не выдумана: `/company/inn-<ИНН>`
даёт 404 (проверено на трёх ИНН), рабочий путь — поиск по ИНН, переход на карточку, затем
`/contacts`. Проверено живьём: ПАО «ОДК-КУЗНЕЦОВ» → сайт, 3 телефона, 3 почты.

ДВЕ СТРАНИЦЫ, А НЕ ОДНА. Проба показала: на `/contacts` есть сайт, телефоны, почты, но НЕТ
выручки и ОКВЭД — они на самой карточке. Берём обе, иначе просьба 1-й сессии (3 447 ИНН на
выручку и ОКВЭД) закрыта не будет.

КАЖДОЕ ПОЛЕ СО ССЫЛКОЙ НА СТРАНИЦУ, где оно взято, — правило владельца: ссылка обязана
вести на доказательство. Строк без ссылки не пишем.

Запуск: python park_checko_sbor.py <файл_целей.csv> <бюджет_сек> <поток.jsonl>
"""
import io
import json
import os
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import requests

DROP = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
TOKEN = os.environ.get('DROP_TOKEN', '')
CELI = sys.argv[1] if len(sys.argv) > 1 else 'PARK-CELI-CHECKO-2S.csv'
BYUDZHET = float(sys.argv[2]) if len(sys.argv) > 2 else 600.0
POTOK = sys.argv[3] if len(sys.argv) > 3 else 'PARK-CHECKO-2S.jsonl'
NACHALO = time.time()
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}


def drop_get(imya):
    r = urllib.request.Request(f'{DROP}/{imya}', headers={'X-Drop-Token': TOKEN})
    return urllib.request.urlopen(r, timeout=180).read()


def drop_put(imya, telo):
    r = urllib.request.Request(f'{DROP}/{imya}', data=telo, method='PUT',
                               headers={'X-Drop-Token': TOKEN})
    return urllib.request.urlopen(r, timeout=300).read()


def tekst(h):
    h = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', h)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))


TEL = re.compile(r'\+7[\s(]?\d{3}[\s)]?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}')
POCHTA = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,6}')
SAYT = re.compile(r'(?:Сайт|Веб-сайт)[^a-zA-Z0-9]{0,25}((?:https?://)?[a-zA-Z0-9-]+'
                  r'(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,6})')
VYRUCHKA = re.compile(r'Выручка[^0-9\-]{0,60}(-?[\d\s.,]{1,20})\s*(млн|млрд|тыс)?\s*'
                      r'(?:руб|₽)', re.I)
GOD = re.compile(r'за\s+(\d{4})\s*год|(\d{4})\s*год', re.I)
# ВСЕ КОДЫ ОКВЭД, а не основной: слово владельца «все коды оквед нужны».
# Первая версия требовала тире между кодом и названием и дала НОЛЬ на 265 карточках —
# в тексте без тегов разделителя может не быть вовсе. Поэтому: находим РАЗДЕЛ видов
# деятельности и вынимаем оттуда все коды подряд, а название берём до следующего кода.
RAZDEL_OKVED = re.compile(r'(?:Виды\s+деятельности|ОКВЭД|Коды\s+ОКВЭД|'
                          r'Основной\s+вид\s+деятельности)', re.I)
KOD_OKVED = re.compile(r'(\d{2}\.\d{2}(?:\.\d{1,2})?)\s*[—–\-:.]?\s*'
                       r'([А-ЯЁа-яё][^|]{3,110}?)(?=\s+\d{2}\.\d{2}\b|\s*$)')


def okvedy(t):
    """Список (код, название) из раздела видов деятельности. Пусто — значит пусто."""
    m = RAZDEL_OKVED.search(t)
    if not m:
        return []
    kusok = t[m.start():m.start() + 6000]
    out, vidal = [], set()
    for kod, imya in KOD_OKVED.findall(kusok):
        imya = ' '.join(imya.split())[:110].strip(' .,;')
        if kod in vidal:
            continue
        vidal.add(kod)
        out.append((kod, imya))
    return out
REGION = re.compile(r'(?:Регион|Адрес)[^А-Яа-я]{0,20}([А-Яа-я][^,]{2,40})')
# Мусорные почты, которые лежат на КАЖДОЙ странице чеко и к предприятию не относятся.
CHUZHIE = re.compile(r'@checko\.|@yandex\.ru$|noreply|support@|example', re.I)

zamok = threading.Lock()
sch = {'целей': 0, 'карточек': 0, 'сайт': 0, 'телефоны': 0, 'почты': 0,
       'выручка': 0, 'оквэд': 0, 'нет карточки': 0, 'сбоев': 0}


def main():
    stroki = drop_get(CELI).decode('utf-8-sig', 'replace').splitlines()[1:]
    celi = []
    for s in stroki:
        ch = s.split(';')
        if ch and ch[0].strip().isdigit():
            celi.append((ch[0].strip(), (ch[1] if len(ch) > 1 else '').strip('"')))
    gotovo = set()
    try:
        for l in drop_get(POTOK).decode('utf-8', 'replace').splitlines():
            try:
                gotovo.add(json.loads(l)['inn'])
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    celi = [c for c in celi if c[0] not in gotovo]
    px = []
    for s in drop_get('dolphin-proxies.txt').decode('utf-8', 'replace').splitlines():
        s = s.strip()
        if s and '@' in s:
            px.append(s if s.startswith('socks5') else 'socks5://' + s)
    sch['целей'] = len(celi)
    print(json.dumps({'к обходу': len(celi), 'уже сделано': len(gotovo),
                      'прокси': len(px)}, ensure_ascii=False), flush=True)
    f = io.open(os.path.basename(POTOK), 'w', encoding='utf-8')

    def odna(t):
        idx, (inn, imya) = t
        if time.time() - NACHALO > BYUDZHET:
            return
        p = px[idx % len(px)] if px else None
        pr = {'http': p, 'https': p} if p else None
        try:
            r = requests.get(f'https://checko.ru/search?query={inn}', headers=UA, timeout=40,
                             allow_redirects=True, proxies=pr)
            if r.status_code != 200 or '/company/' not in str(r.url):
                with zamok:
                    sch['нет карточки'] += 1
                return
            kartochka = str(r.url).split('?')[0].rstrip('/')
            if kartochka.endswith('/contacts'):
                kartochka = kartochka[:-len('/contacts')]
            t_kart = tekst(r.text)
            rc = requests.get(kartochka + '/contacts', headers=UA, timeout=40, proxies=pr)
            t_kon = tekst(rc.text) if rc.status_code == 200 else ''
        except Exception as e:  # noqa: BLE001
            with zamok:
                sch['сбоев'] += 1
            return
        sayt = SAYT.findall(t_kon) + SAYT.findall(t_kart)
        tel = [x for x in dict.fromkeys(TEL.findall(t_kon) + TEL.findall(t_kart))]
        poch = [x for x in dict.fromkeys(POCHTA.findall(t_kon) + POCHTA.findall(t_kart))
                if not CHUZHIE.search(x)]
        vyr = VYRUCHKA.search(t_kart)
        god = GOD.search(t_kart[max(0, vyr.start() - 120):vyr.start() + 120]) if vyr else None
        okv = okvedy(t_kart) or okvedy(t_kon)
        zap = {'inn': inn, 'predpriyatie': imya,
               'kartochka': kartochka,
               'sayt': (sayt[0] if sayt else ''),
               'telefony': tel[:8], 'pochty': poch[:8],
               'vyruchka': (vyr.group(1).strip() + ' ' + (vyr.group(2) or '')).strip() if vyr else '',
               'vyruchka_god': (god.group(1) or god.group(2)) if god else '',
               'okved': (okv[0][0] + ' — ' + okv[0][1]) if okv else '',
               'okved_kody': [a for a, _ in okv],
               'okved_all': ' | '.join(a + ' ' + b for a, b in okv),
               'okvedov': len(okv),
               'ssylka_kontakty': kartochka + '/contacts',
               'ssylka_kartochka': kartochka,
               'istochnik': 'checko.ru, карточка компании'}
        with zamok:
            sch['карточек'] += 1
            if zap['sayt']:
                sch['сайт'] += 1
            if tel:
                sch['телефоны'] += 1
            if poch:
                sch['почты'] += 1
            if zap['vyruchka']:
                sch['выручка'] += 1
            if zap['okved']:
                sch['оквэд'] += 1
            f.write(json.dumps(zap, ensure_ascii=False) + '\n')
            f.flush()
            if sch['карточек'] % 50 == 0:
                print(json.dumps(sch, ensure_ascii=False), flush=True)

    with ThreadPoolExecutor(max_workers=24) as pool:
        list(pool.map(odna, list(enumerate(celi))))
    f.close()
    # Поток дописываем к тому, что уже лежит на дропе: перезапись стёрла бы прошлые заходы.
    staroe = b''
    try:
        staroe = drop_get(POTOK)
    except Exception:  # noqa: BLE001
        pass
    novoe = io.open(os.path.basename(POTOK), 'rb').read()
    drop_put(POTOK, staroe + novoe)
    print(json.dumps(sch, ensure_ascii=False), flush=True)


main()
