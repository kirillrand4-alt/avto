# -*- coding: utf-8 -*-
"""checko через пул socks5 — с проверочного VPS, где пул достижим.

Первый заход ПРОБНЫЙ: берём несколько ИНН и печатаем, что вообще отдаёт карточка, чтобы
вынималки строились по живой странице, а не по памяти. Ничего не парсим вслепую.
Запуск: python park_checko_vps.py <сколько_ИНН>
"""
import io
import json
import os
import re
import sys
import urllib.request

try:
    import requests
except ImportError:
    requests = None

DROP = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
TOKEN = os.environ.get('DROP_TOKEN', '')
SKOLKO = int(sys.argv[1]) if len(sys.argv) > 1 else 3


def drop_get(imya):
    r = urllib.request.Request(f'{DROP}/{imya}', headers={'X-Drop-Token': TOKEN})
    return urllib.request.urlopen(r, timeout=120).read()


def proxies():
    out = []
    for s in drop_get('dolphin-proxies.txt').decode('utf-8', 'replace').splitlines():
        s = s.strip()
        if s and '@' in s:
            out.append('socks5://' + s if not s.startswith('socks5') else s)
    return out


def main():
    if requests is None:
        print(json.dumps({'ошибка': 'на VPS нет requests'}, ensure_ascii=False))
        return
    px = proxies()
    print(json.dumps({'прокси в пуле': len(px)}, ensure_ascii=False))
    inny = [x.strip() for x in drop_get('DLYA-SOSEDA-CHECKO-vyruchka-okved.csv')
            .decode('utf-8-sig', 'replace').splitlines()[1:] if x.strip()]
    inny = [x.split(';')[0] for x in inny][:SKOLKO]
    UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                        '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    for n, inn in enumerate(inny):
        p = px[n % len(px)] if px else None
        # ФОРМА АДРЕСА ВЗЯТА ИЗ ГОТОВОГО `srv-checko_contacts.py`, а не придумана:
        # `/company/inn-<ИНН>` даёт 404 (проверено на трёх ИНН, страница «не найдена»),
        # рабочий путь — поиск по ИНН с переходом на карточку, дальше /contacts.
        u = f'https://checko.ru/search?query={inn}'
        try:
            r = requests.get(u, headers=UA, timeout=45, allow_redirects=True,
                             proxies={'http': p, 'https': p} if p else None)
            if '/company/' in str(r.url) and not str(r.url).rstrip('/').endswith('/contacts'):
                baza = str(r.url).split('?')[0].rstrip('/')
                r2 = requests.get(baza + '/contacts', headers=UA, timeout=45,
                                  proxies={'http': p, 'https': p} if p else None)
                if r2.status_code == 200:
                    r = r2
            t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', r.text))
            vyr = re.findall(r'[Вв]ыручка[^0-9]{0,40}([\d\s.,]{4,20})\s*(млн|млрд|тыс|руб)', t)
            okv = re.findall(r'(\d\d\.\d\d(?:\.\d\d?)?)\s*[—-]\s*([А-Яа-я][^|]{5,60})', t[:6000])
            sayt = re.findall(r'(?:Сайт|сайт)[^a-zA-Z]{0,20}([a-zA-Z0-9.-]+\.[a-zA-Z]{2,6})', t)
            tel = re.findall(r'(\+7[\s(]?\d{3}[\s)]?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2})', t)
            pochta = re.findall(r'[a-zA-Z0-9._%-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,6}', t)
            print(json.dumps({'инн': inn, 'http': r.status_code, 'адрес': str(r.url)[:80],
                              'знаков': len(r.text),
                              'выручка': vyr[:2], 'оквэд': okv[:2], 'сайт': sayt[:2],
                              'телефоны': tel[:3], 'почты': pochta[:3],
                              'кусок': t[:300]}, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            print(json.dumps({'инн': inn, 'ошибка': str(e)[:160]}, ensure_ascii=False))


main()
