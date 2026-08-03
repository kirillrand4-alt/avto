# -*- coding: utf-8 -*-
"""Обход сайтов НАСТОЯЩИМ браузером — из песочницы, не занимая сервер.

ЗАЧЕМ. Проба показала: из 30 доменов, с которых обычный обходчик получил ноль страниц,
11 спокойно ОТКРЫВАЮТСЯ в браузере. Значит дело было в обходчике, а не в защите, и это
11 предприятий с известным сайтом, у которых контакты просто не собраны.

ПОЧЕМУ ЗДЕСЬ, А НЕ ЧЕРЕЗ РАННЕР. Очередь тяжёлых задач сервера однопоточная, там уже идут
справочники подразделений. Chromium в песочнице стоит (PLAYWRIGHT_BROWSERS_PATH), выдачу
этот обход не трогает — значит он единственный, который сейчас реально параллелен всему.

Берём не только главную: страницы контактов и руководства, где люди и живут.
"""
import json, os, re, sys, time
from playwright.sync_api import sync_playwright

DOM = json.load(open('molchat-proverka.json', encoding='utf-8'))
OTKRYLIS = [x['domen'] for x in DOM if 'ОТКРЫЛСЯ' in x['itog']]
PUTI = ['', '/contacts', '/kontakty', '/contact', '/about/contacts', '/o-kompanii/kontakty',
        '/rukovodstvo', '/about/management', '/company/management', '/struktura']
TEL = re.compile(r'\(?(?:\+7|\b8)\)?[\s(\-]*\d{3,5}[\s)\-]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}\b'
                 r'|\(\d{3,5}\)[\s\-]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}\b')
POCHTA = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
FIO = re.compile(r'\b([А-ЯЁ][а-яё\-]{2,})\s+([А-ЯЁ][а-яё]{2,})\s+'
                 r'([А-ЯЁ][а-яё]*(?:ович|евич|ьевич|овна|евна|ьевна|ична|инична))\b')
DOLZH = re.compile(r'(главн\w+\s+(?:инженер\w*|энергетик\w*|механик\w*|технолог\w*)|'
                   r'техническ\w+\s+директор\w*|директор\w*\s+по\s+производств\w+|'
                   r'начальник\w*\s+(?:цеха|производств\w+|отдела|управлени\w+|службы)|'
                   r'заместител\w+\s+главн\w+\s+инженер\w*)', re.I)

out, log = [], []
with sync_playwright() as pw:
    # Playwright из pip ждёт свою версию браузера, а в песочнице стоит другая сборка.
    # Качать вторую бессмысленно и запрещено окружением — указываем готовую напрямую.
    br = pw.chromium.launch(headless=True,
                            executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
                            args=['--no-sandbox', '--disable-dev-shm-usage'])
    for d in OTKRYLIS:
        ctx = br.new_context(user_agent=(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'), locale='ru-RU')
        pg = ctx.new_page()
        stranic = 0
        for put in PUTI:
            try:
                pg.goto(f'https://{d}{put}', timeout=25000, wait_until='domcontentloaded')
                pg.wait_for_timeout(1200)
                t = re.sub(r'\s+', ' ', pg.inner_text('body'))
            except Exception:  # noqa: BLE001
                continue
            if len(t) < 200:
                continue
            stranic += 1
            for m in FIO.finditer(t):
                fio = f'{m.group(1)} {m.group(2)} {m.group(3)}'
                okno = t[max(0, m.start() - 200):m.start() + 300]
                dl = DOLZH.search(okno)
                tel = [x.group(0) for x in TEL.finditer(okno)]
                poch = [x.group(0) for x in POCHTA.finditer(okno)]
                if dl or tel or poch:
                    out.append({'domen': d, 'stranica': f'https://{d}{put}', 'fio': fio,
                                'dolzhnost': dl.group(1) if dl else '',
                                'telefony': tel[:2], 'pochty': poch[:2],
                                'citata': okno[:220]})
            # контакты без имени рядом тоже нужны: приёмная это путь к человеку
            for m in TEL.finditer(t):
                okno = t[max(0, m.start() - 160):m.start() + 60]
                if not FIO.search(okno):
                    out.append({'domen': d, 'stranica': f'https://{d}{put}', 'fio': '',
                                'dolzhnost': '', 'telefony': [m.group(0)], 'pochty': [],
                                'citata': okno[:220]})
        ctx.close()
        s_imenem = sum(1 for x in out if x['domen'] == d and x['fio'])
        log.append(f'{d}: страниц {stranic}, записей {sum(1 for x in out if x["domen"]==d)}, '
                   f'из них с ФИО {s_imenem}')
        print(log[-1], file=sys.stderr, flush=True)
    br.close()

json.dump(out, open('obhod-brauzerom.json', 'w', encoding='utf-8'), ensure_ascii=False)
print(f'\nвсего записей {len(out)}, с ФИО {sum(1 for x in out if x["fio"])}, '
      f'с должностью {sum(1 for x in out if x["dolzhnost"])}, '
      f'доменов {len(OTKRYLIS)}', file=sys.stderr)
