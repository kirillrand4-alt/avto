# -*- coding: utf-8 -*-
"""ЗАМЕР, а не выгрузка: что на самом деле лежит на карточках закупок пяти площадок.

ЗАЧЕМ ОТДЕЛЬНЫЙ МОДУЛЬ. Я заявил владельцу, что 277 тысяч собранных карточек «дадут фамилии
и общие линии, а не сотовые». Основание было — ПЯТНАДЦАТЬ карточек: по три на четырёх
площадках плюс три на РТС. Это ровно тот класс вывода, который я сам ловлю у соседей:
отрицательный вывод по крошечной выборке, поданный как свойство источника. Вывод отозван,
здесь он проверяется числами.

ЧТО СЧИТАЕМ на каждой карточке:
    есть ли ФИО, есть ли телефон, МОБИЛЬНЫЙ ли телефон,
    и — главное — сколько РАЗНЫХ людей стоит на одном номере.
Последнее решает всё: номер, общий для трёх человек, это линия отдела, а не личный телефон,
и в главную меру он не идёт. Именно так Росэлторг и провалился на трёх карточках — но три
карточки не доказательство, а гипотеза.

ВЫБОРКА ЧЕСТНАЯ. Карточки берутся не подряд (подряд — это одно предприятие и одна секция),
а равномерно по всем предприятиям площадки: сначала по одной с каждого, потом второй круг.
Сколько взято и сколько всего — печатается, молчаливых потолков нет.

РЕЦЕПТЫ сняты агентами с живых карточек и проверены независимой попыткой опровержения.
Ловушки, каждая из которых уже стоила нам разбора:
  * РТС: на карточке ДВА блока контактов — ОРГАНИЗАТОР и ЗАКАЗЧИК. ФИО лежит только у
    организатора, а организатор — это не наше предприятие. Считаем оба раздельно.
  * РТС: та же строка второй раз лежит в скрытом мобильном дубле, без дедупа счётчики
    удваиваются вдвое.
  * РТС: `http_status` 503 у ВСЕХ ответов, включая целые; `data_found` true даже у
    несуществующей карточки. Живую карточку опознаём по заголовку «Тендер <номер>:».
  * Портал: адрес карточки `/need/<id>`, а не `/purchase/<id>`; контакт берётся не со
    страницы, а из `newapi/api/Need/Get?needId=` — хост БЕЗ префикса `old`.
  * ЭТП ГПБ: одиночного JSON-роута карточки нет (404), только страница целиком.

Использование:
    python3 zamer_kontaktov.py --ploshchadka etpgpb --skolko 60
    python3 zamer_kontaktov.py --vse --skolko 60 --potok 4
"""
import csv
import html as htmlmod
import json
import os
import re
import subprocess
import sys
import threading
import urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
C = os.path.join(L, 'centro')
KLIENT = os.path.join(BAZA, 'server', 'run_on_server.py')
VYHOD = os.path.join(C, 'ZAMER-kontaktov-na-kartochkah.csv')
COLS = ['ploshchadka', 'inn', 'predpriyatie', 'nomer', 'ssylka', 'chey_kontakt', 'fio',
        'telefon', 'pochta', 'mobilnyy', 'sboy']


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


def chitat(put):
    return list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(put) else []


def mobilnyy(t):
    c = re.sub(r'\D', '', t or '')
    if len(c) == 11 and c[0] in '78':
        c = c[1:]
    return len(c) == 10 and c[0] == '9'


def probe(url, wait=8000, cap=1300000, tayminaut=420):
    zad = {'url': url, 'screenshot': False, 'proxy': '', 'return_html': True,
           'html_cap': cap, 'wait_ms': wait}
    try:
        p = subprocess.run([sys.executable, KLIENT, 'browser_probe',
                            json.dumps(zad, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=tayminaut)
    except subprocess.TimeoutExpired:
        return None, None, f'раннер не ответил за {tayminaut} с'
    try:
        d = json.loads(p.stdout[p.stdout.index('{'):]).get('data') or {}
    except (ValueError, json.JSONDecodeError):
        return None, None, (p.stdout or p.stderr or 'пусто')[-160:]
    h = d.get('html') or ''
    if not h:
        return None, d, f"тело пусто | error={str(d.get('error'))[:90]}"
    return h, d, ''


def bez_tegov(t):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', htmlmod.unescape(t or ''))).strip()


# ------------------------------------------------------------------ разборщики по площадкам
def etpgpb(ssylka):
    h, d, err = probe(ssylka, wait=9000)
    if h is None:
        return [], err
    # Значения видны и в тексте страницы, и в сыром состоянии Nuxt. Берём текст: имена полей
    # devalue-состояния меняются со сборкой, подписи на странице — нет.
    t = bez_tegov(h)
    fio = re.search(r'Контактное лицо\s+([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2})', t)
    tel = re.search(r'Контактный телефон\s+([0-9()+\-\s]{6,30})', t)
    poc = re.search(r'Адрес электронной почты\s+(\S+@\S+)', t)
    if not (fio or tel or poc):
        return [], ''
    return [{'chey': 'заказчик', 'fio': fio.group(1) if fio else '',
             'tel': (tel.group(1) if tel else '').strip(),
             'poc': poc.group(1) if poc else ''}], ''


def roseltorg(ssylka):
    h, d, err = probe(ssylka, wait=8000)
    if h is None:
        return [], err
    out = {}
    for pole, klass in (('fio', 'procedure-organizer-contact-fio'),
                        ('tel', 'procedure-organizer-contact-phone'),
                        ('poc', 'procedure-organizer-contact-email')):
        m = re.search(klass + r'[^"]*"[\s\S]{0,600}?lot-common-info__value[^>]*>([\s\S]{0,200}?)<',
                      h)
        out[pole] = bez_tegov(m.group(1)) if m else ''
    if not any(out.values()):
        return [], ''
    return [{'chey': 'организатор торгов', **out}], ''


def portal(ssylka):
    m = re.search(r'/(\d{4,})', ssylka or '')
    if not m:
        return [], 'в ссылке нет кода'
    h, d, err = probe('https://zakupki.mos.ru/newapi/api/Need/Get?needId=' + m.group(1),
                      wait=4000, cap=900000)
    if h is None:
        return [], err
    i, j = h.find('<pre>'), h.rfind('</pre>')
    kus = htmlmod.unescape(h[i + 5:j] if i >= 0 and j > i else h)
    try:
        o = json.loads(kus)
    except json.JSONDecodeError:
        # 404 у площадки честный: тело с message, а не пустая разметка
        return [], ('карточки нет' if 'E_vo' in kus or '404' in kus[:200]
                    else 'ответ не JSON: ' + kus[:90])
    if not isinstance(o, dict):
        return [], 'ответ не объект'
    return [{'chey': 'заказчик', 'fio': str(o.get('contactPerson') or ''),
             'tel': str(o.get('contactPhone') or ''),
             'poc': str(o.get('contactEmail') or '')}], ''


def tektorg(ssylka):
    h, d, err = probe(ssylka, wait=8000)
    if h is None:
        return [], err
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>([\s\S]{100,}?)</script>', h)
    if not m:
        return [], 'нет __NEXT_DATA__'
    try:
        o = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        return [], f'__NEXT_DATA__ не разобран: {str(e)[:60]}'
    pi = ((o.get('props') or {}).get('pageProps') or {}).get('procedureItem')
    if not isinstance(pi, dict):
        stranica = (o.get('page') or '')
        return [], ('карточки нет (page=' + stranica + ')' if stranica == '/404'
                    else 'нет procedureItem')
    return [{'chey': 'заказчик', 'fio': str(pi.get('contactPerson') or ''),
             'tel': str(pi.get('contactPhone') or ''),
             'poc': str(pi.get('contactEmail') or '')}], ''


RTS_BLOK = re.compile(r'card-item__organization-title">(ОРГАНИЗАТОР|ЗАКАЗЧИК)([\s\S]{0,3000}?)'
                      r'(?=card-item__organization-title">|$)')
RTS_KONT = re.compile(r'Контактные данные:\s*</span>([\s\S]{0,220}?)</p>')


def rts(ssylka):
    # wait 30 с: на 20 с одна карточка из трёх возвращает пустое тело — это неудавшийся
    # съём, а не отсутствие данных.
    h, d, err = probe(ssylka, wait=30000)
    if h is None:
        return [], err
    if 'card-item__organization-title">ЗАКАЗЧИК' not in h:
        return [], ('карточки нет' if not str(d.get('title') or '').startswith('Тендер')
                    else '')
    out, bylo = [], set()
    for m in RTS_BLOK.finditer(h):
        chey = 'организатор' if m.group(1) == 'ОРГАНИЗАТОР' else 'заказчик'
        for k in RTS_KONT.finditer(m.group(2)):
            stroka = bez_tegov(k.group(1))
            # скрытый мобильный дубль даёт ту же строку второй раз
            if not stroka or (chey, stroka) in bylo:
                continue
            bylo.add((chey, stroka))
            # Позиционно разбирать нельзя: порядок токенов плавает. Классифицируем по виду.
            fio = tel = poc = ''
            for tok in re.split(r'[;|]', stroka):
                tok = tok.strip()
                if not tok:
                    continue
                if '@' in tok:
                    poc = poc or tok
                elif re.fullmatch(r'[А-ЯЁа-яё .]{6,60}', tok) and len(tok.split()) >= 2:
                    fio = fio or tok
                elif re.search(r'\d{5,}', tok):
                    tel = tel or tok
            out.append({'chey': chey, 'fio': fio, 'tel': tel, 'poc': poc})
    return out, ''


PLOSHCHADKI = {
    'etpgpb': ('ЭТП ГПБ', 'etpgpb-po-kompaniyam.csv', etpgpb),
    'roseltorg': ('Росэлторг', 'roseltorg-po-kompaniyam.csv', roseltorg),
    'portal': ('Портал Москвы', 'portal-po-kompaniyam-inn.csv', portal),
    'tektorg': ('ТЭК-Торг', 'tektorg-po-kompaniyam.csv', tektorg),
    'rts': ('РТС-тендер', 'rts-po-kompaniyam.csv', rts),
}


def vyborka_vglub(rows, skolko, predpriyatiy=6):
    """Много карточек НЕМНОГИХ предприятий — для вопроса про ОБЩИЕ номера.

    Обычная выборка (по одной карточке с предприятия) отвечает на «какая доля карточек несёт
    мобильный», но общий номер увидеть НЕ МОЖЕТ: чтобы номер повторился у двух людей, нужны
    две карточки ОДНОГО предприятия, а их там нет. Замер 04.08 дал по такой выборке «общих
    номеров ноль», а первый же улов на 98 человек нашёл восемь. Ноль означал «не смотрели».
    """
    po_inn = defaultdict(list)
    for r in rows:
        if r.get('ssylka'):
            po_inn[r.get('inn') or ''].append(r)
    krupnye = sorted(po_inn, key=lambda i: -len(po_inn[i]))[:predpriyatiy]
    na_kazhdoe = max(1, skolko // max(1, len(krupnye)))
    out = []
    for inn in krupnye:
        out.extend(po_inn[inn][:na_kazhdoe])
    return out[:skolko]


def vyborka(rows, skolko):
    """Равномерно по предприятиям, а не подряд: подряд — это одно предприятие и одна секция."""
    po_inn = defaultdict(list)
    for r in rows:
        if r.get('ssylka'):
            po_inn[r.get('inn') or ''].append(r)
    out, krug = [], 0
    while len(out) < skolko:
        dobavleno = 0
        for inn in sorted(po_inn):
            if krug < len(po_inn[inn]):
                out.append(po_inn[inn][krug])
                dobavleno += 1
                if len(out) >= skolko:
                    break
        if not dobavleno:
            break
        krug += 1
    return out


def main():
    skolko = dovod('--skolko', 60)
    potok = dovod('--potok', 4)
    # Предел раннера: сверх 30 воркеров задачи не работают, а ждут.
    import predel_rannera
    predel_rannera.preduprezhdenie(potok)
    imena = ([k for k in PLOSHCHADKI] if '--vse' in sys.argv
             else [dovod('--ploshchadka', 'etpgpb')])

    novyy = not os.path.exists(VYHOD) or os.path.getsize(VYHOD) == 0
    f = open(VYHOD, 'a', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy:
        w.writeheader()
    lock = threading.Lock()

    for imya in imena:
        nazvanie, fajl, razbor = PLOSHCHADKI[imya]
        rows = chitat(os.path.join(C, fajl))
        vglub = '--vglub' in sys.argv
        celi = (vyborka_vglub(rows, skolko) if vglub else vyborka(rows, skolko))
        print(f'\n[{nazvanie}] всего карточек {len(rows)}, беру {len(celi)} '
              f'по {len({r.get("inn") for r in celi})} предприятиям'
              + (' — ВГЛУБЬ (для вопроса про общие номера)' if vglub else
                 ' — вширь (для вопроса про долю мобильных; общие номера такая выборка '
                 'увидеть НЕ МОЖЕТ)'), file=sys.stderr)
        if not celi:
            continue
        sch = {'карточек': 0, 'с ФИО': 0, 'с телефоном': 0, 'мобильных': 0, 'пусто': 0,
               'сбоев': 0}
        po_nomeru = defaultdict(set)

        def odna(r):
            try:
                return r, razbor(r['ssylka'])
            except Exception as e:
                return r, ([], f'исключение: {str(e)[:90]}')

        with ThreadPoolExecutor(max_workers=potok) as pool:
            for r, (lyudi, err) in pool.map(odna, celi):
                with lock:
                    sch['карточек'] += 1
                    if err:
                        sch['сбоев'] += 1
                        w.writerow({'ploshchadka': nazvanie, 'inn': r.get('inn'),
                                    'predpriyatie': r.get('predpriyatie'),
                                    'nomer': r.get('nomer'), 'ssylka': r.get('ssylka'),
                                    'sboy': err[:150]})
                        continue
                    if not lyudi:
                        sch['пусто'] += 1
                    for x in lyudi:
                        if x['fio']:
                            sch['с ФИО'] += 1
                        if x['tel']:
                            sch['с телефоном'] += 1
                        mob = mobilnyy(x['tel'])
                        if mob:
                            sch['мобильных'] += 1
                        if x['tel'] and x['fio']:
                            po_nomeru[re.sub(r'\D', '', x['tel'])[-10:]].add(
                                x['fio'].strip().lower())
                        w.writerow({'ploshchadka': nazvanie, 'inn': r.get('inn'),
                                    'predpriyatie': r.get('predpriyatie'),
                                    'nomer': r.get('nomer'), 'ssylka': r.get('ssylka'),
                                    'chey_kontakt': x['chey'], 'fio': x['fio'],
                                    'telefon': x['tel'], 'pochta': x['poc'],
                                    'mobilnyy': 'да' if mob else '', 'sboy': ''})
                    f.flush()
        obshchie = {n: l for n, l in po_nomeru.items() if len(l) > 1}
        lyudej_na_obshchih = sum(len(l) for l in obshchie.values())
        print(f'  {sch}', file=sys.stderr)
        print(f'  номеров, стоящих у РАЗНЫХ людей: {len(obshchie)} '
              f'(на них {lyudej_na_obshchih} человек) — такой номер не личный',
              file=sys.stderr)
        if sch['карточек']:
            print(f'  доля карточек с мобильным: '
                  f'{sch["мобильных"] * 100 // sch["карточек"]} %', file=sys.stderr)
    f.close()
    print(f'\n→ {VYHOD}', file=sys.stderr)


if __name__ == '__main__':
    main()
