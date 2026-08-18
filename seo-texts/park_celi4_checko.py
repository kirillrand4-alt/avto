# -*- coding: utf-8 -*-
"""Четыре адресные цели владельца: контакты с карточки чеко + люди с сайта.

Роли по заданию, в порядке важности: главный инженер и технический директор, служба
качества (директор/специалист по качеству), потом снабжение. Отдельно ищем «Феликс
Николаевич» — технический директор Дмитровских колбас, названный владельцем.
"""
import io, json, os, re, sys, urllib.parse, urllib.request
import requests

DROP = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
TOKEN = os.environ.get('DROP_TOKEN', '')
CELI = [('Брянский молочный комбинат', ''), ('Хлебокомбинат ПЕКО', ''),
        ('МАЯК Хлеб-соль', '3811125221'), ('Дмитровские колбасы', '')]
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}


def dg(i):
    return urllib.request.urlopen(urllib.request.Request(
        f'{DROP}/{i}', headers={'X-Drop-Token': TOKEN}), timeout=120).read()


def tekst(h):
    h = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', h)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))


px = ['socks5://' + s.strip() for s in dg('dolphin-proxies.txt').decode('utf-8', 'replace').splitlines() if s.strip() and '@' in s]
TEL = re.compile(r'\+?7[\s(-]?\d{3}[\s)-]?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}')
POCHTA = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,6}')
SAYT = re.compile(r'(?:Сайт|Веб-сайт)[^a-zA-Z0-9]{0,25}((?:https?://)?[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,6})')

for n, (imya, inn) in enumerate(CELI):
    p = px[n % len(px)] if px else None
    pr = {'http': p, 'https': p} if p else None
    zapros = inn or imya
    try:
        r = requests.get('https://checko.ru/search?query=' + urllib.parse.quote(zapros),
                         headers=UA, timeout=45, allow_redirects=True, proxies=pr)
        url = str(r.url)
        # ПОИСК ПО НАЗВАНИЮ УВОДИТ НА СТРАНИЦУ ВЫБОРА `/company/select`, а не на карточку:
        # тёзок много. Разбираем список и берём того, чьё имя ближе к запросу; если
        # однозначного нет — печатаем ВСЕХ кандидатов, а не молча берём первого.
        if '/company/' not in url or url.rstrip('/').endswith('/select'):
            kand = []
            for m in re.finditer(r'href="(/company/[^"?#]+)"[^>]*>(.{0,160}?)</a>', r.text, re.S):
                nm = ' '.join(re.sub(r'<[^>]+>', ' ', m.group(2)).split())
                if nm and m.group(1) not in [k[0] for k in kand]:
                    kand.append((m.group(1), nm))
            if not kand:
                print(json.dumps({'цель': imya, 'итог': 'карточка не найдена'}, ensure_ascii=False), flush=True)
                continue
            klyuch = [w.lower() for w in re.findall(r'[А-Яа-яЁёA-Za-z]{4,}', imya)]
            def ves(t):
                nn = t[1].lower()
                return sum(1 for w in klyuch if w in nn)
            kand.sort(key=ves, reverse=True)
            print(json.dumps({'цель': imya, 'кандидатов': len(kand),
                              'первые': [k[1][:70] for k in kand[:5]]}, ensure_ascii=False), flush=True)
            url = 'https://checko.ru' + kand[0][0]
            r = requests.get(url, headers=UA, timeout=45, proxies=pr)
        baza = url.split('?')[0].rstrip('/')
        if baza.endswith('/contacts'):
            baza = baza[:-9]
        tk = tekst(r.text)
        rc = requests.get(baza + '/contacts', headers=UA, timeout=45, proxies=pr)
        tc = tekst(rc.text) if rc.status_code == 200 else ''
        inn_naydn = re.search(r'ИНН[^0-9]{0,10}(\d{10}|\d{12})', tk)
        ruk = re.search(r'(?:Руководитель|Генеральный директор|Директор)[^А-ЯЁ]{0,20}'
                        r'([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)', tk)
        print(json.dumps({'цель': imya, 'карточка': baza,
                          'инн': inn_naydn.group(1) if inn_naydn else '',
                          'руководитель': ruk.group(1) if ruk else '',
                          'сайт': (SAYT.findall(tc) + SAYT.findall(tk))[:1],
                          'телефоны': list(dict.fromkeys(TEL.findall(tc) + TEL.findall(tk)))[:6],
                          'почты': [x for x in dict.fromkeys(POCHTA.findall(tc) + POCHTA.findall(tk))
                                    if 'checko' not in x][:6]}, ensure_ascii=False), flush=True)
    except Exception as e:
        print(json.dumps({'цель': imya, 'ошибка': str(e)[:150]}, ensure_ascii=False), flush=True)
