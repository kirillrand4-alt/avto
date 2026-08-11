# -*- coding: utf-8 -*-
"""Догружает реквизиты с checko в карточки базы обзвона: регион, адрес, директор, сайт, деньги.

Владелец открыл карточку АО «РКЦ Прогресс», которую я только что отдал продавцу, и обвёл
пустые поля: Регион, Адрес, Директор, Сайт, Чистая прибыль, Сотрудники. Сказал коротко:
«и заполни информацию из чеко».

Справедливо: карточка собиралась из park_panel.db, а там этих полей нет вовсе — парк знает
машину и доказательство, а реквизиты живут на checko.

Ходим через МОБИЛЬНЫЙ прокси: общий пул из 78 адресов я сам посадил на заслон 429, а
мобильный 194.143.150.98 отдаёт 200. При заслоне дёргается ссылка переподключения — меняем
IP и продолжаем, а не долбим.

Разбор полей взят из прибора соседки `park_checko_sbor.py`, а не написан заново: её
регулярки уже отбиты на 2 961 карточке, и переписывать их значит платить ту же цену дважды.
Своё здесь одно — раздел «Руководитель» и ССЧ, которых у неё в разборе не было.

Пишем ТОЛЬКО В ПУСТОЕ: у карточки может быть своя работа продавца, и затирать её нельзя.

Запуск на сервере: python C:\\sender\\_ops\\park_1s_checko_kartochka.py <бюджет_секунд>
"""
import io
import json
import os
import re
import sys
import time

import requests

MOBILNYY = 'socks5://kirillrand4:39476861@194.143.150.98:1650'
SMENA_IP = ('https://lk.lte-center.ru/api/proxies/24097/reconnect-link/'
            '722df0f668deb381c2da4548e1f044f4')
SPISOK = r'C:\sender\_centro_inny.json'
VYHOD = r'C:\sender\park_1s_checko_kartochka.jsonl'
BAZA = r'C:\seostat\data\centrifugal.db'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
BYUDZHET = float(sys.argv[1]) if len(sys.argv) > 1 else 600.0
NACHALO = time.time()

OGRN = re.compile(r'/company/(?:[^/"?]*?-)?(\d{13,15})')
TEL = re.compile(r'\+7[\s(]?\d{3}[\s)]?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}')
POCHTA = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,6}')
CHUZHIE = re.compile(r'@checko\.|noreply|support@|example', re.I)
SAYT = re.compile(r'(?:Сайт|Веб-сайт)[^a-zA-Z0-9]{0,25}((?:https?://)?[a-zA-Z0-9-]+'
                  r'(?:\.[a-zA-Z0-9-]+)+)')
ADRES = re.compile(r'(?:Юридический адрес|Адрес)[^\d]{0,25}(\d{6},?\s*[^«»]{10,120}?)'
                   r'(?=\s{2,}|\s(?:Телефон|Сайт|Почта|ОКВЭД|Руковод))')
DIREKTOR = re.compile(r'(?:Руководитель|Генеральный директор|Директор)[^А-ЯЁ]{0,30}'
                      r'([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)')
PRIBYL = re.compile(r'Чистая прибыль[^0-9\-]{0,60}(-?[\d\s.,]{1,20})\s*(млн|млрд|тыс)?')
VYRUCHKA = re.compile(r'Выручка[^0-9\-]{0,60}(-?[\d\s.,]{1,20})\s*(млн|млрд|тыс)?')
SSCH = re.compile(r'(?:Среднесписочная численность|Сотрудник\w*)[^0-9]{0,40}(\d{1,6})')
MNOZH = {'тыс': 1e3, 'млн': 1e6, 'млрд': 1e9}
_smena = [0.0]


def v_rubli(m):
    if not m:
        return None
    try:
        chislo = float(m.group(1).replace('\xa0', '').replace(' ', '').replace(',', '.'))
    except ValueError:
        return None
    return chislo * MNOZH.get((m.group(2) or '').strip(), 1)


def smenit_ip():
    if time.time() - _smena[0] < 25:
        return
    _smena[0] = time.time()
    try:
        requests.get(SMENA_IP, timeout=40)
        time.sleep(12)
    except Exception:  # noqa: BLE001
        pass


def stranica(url):
    """Страница через мобильный прокси. Мобильный канал рвётся — это норма, а не отказ.

    Первый заход считал обрыв связи сбоем и бросал предприятие: 4 из 4 ушли в «сбоев» с
    ConnectionError, хотя ровно та же ссылка через тот же прокси открывалась вручную.
    Поэтому обрыв — повод подождать и повторить, а 429 — повод сменить IP.
    """
    pr = {'http': MOBILNYY, 'https': MOBILNYY}
    posledn = None
    for zahod in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=60, proxies=pr, allow_redirects=True)
        except requests.exceptions.RequestException as e:
            posledn = e
            time.sleep(4 + 4 * zahod)
            continue
        if r.status_code == 429 or 'подтвердите, что вы человек' in r.text:
            smenit_ip()
            continue
        return r
    if posledn is not None:
        raise posledn
    return None


def razobrat(t):
    """Плоский текст карточки -> поля. Ничего не выдумываем: чего нет, того нет."""
    o = {}
    m = ADRES.search(t)
    if m:
        o['adres'] = ' '.join(m.group(1).split())[:200]
        reg = re.match(r'\d{6},?\s*([^,]{3,45})', o['adres'])
        if reg:
            o['region'] = reg.group(1).strip()
    m = DIREKTOR.search(t)
    if m:
        o['direktor'] = ' '.join(m.group(1).split())
    m = SAYT.search(t)
    if m:
        o['sayt'] = m.group(1)
    o['vyruchka'] = v_rubli(VYRUCHKA.search(t))
    o['pribyl'] = v_rubli(PRIBYL.search(t))
    m = SSCH.search(t)
    if m:
        o['ssch'] = int(m.group(1))
    o['telefony'] = sorted({x.strip() for x in TEL.findall(t)})[:10]
    o['pochty'] = sorted({x.lower() for x in POCHTA.findall(t) if not CHUZHIE.search(x)})[:10]
    return o


def main():
    inny = json.load(open(SPISOK, encoding='utf-8'))
    sdelano = set()
    if os.path.exists(VYHOD):
        for ln in io.open(VYHOD, encoding='utf-8', errors='replace'):
            try:
                sdelano.add(json.loads(ln)['inn'])
            except Exception:  # noqa: BLE001
                pass
    import sqlite3
    p = sqlite3.connect(BAZA, timeout=60)
    c = p.cursor()
    kolonki = {x[1] for x in c.execute('pragma table_info(company)')}
    f = io.open(VYHOD, 'a', encoding='utf-8')
    sch = {'взято': 0, 'карточки нет': 0, 'записано полей': 0, 'сбоев': 0}
    for inn in inny:
        if inn in sdelano or time.time() - NACHALO > BYUDZHET:
            continue
        try:
            r = stranica('https://checko.ru/search?query=' + inn)
            if r is None:
                sch['сбоев'] += 1
                continue
            m = OGRN.search(r.url) or OGRN.search(r.text)
            if not m:
                sch['карточки нет'] += 1
                continue
            t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', r.text))
            o = razobrat(t)
            o.update({'inn': inn, 'ogrn': m.group(1), 'ssylka': r.url})
            sch['взято'] += 1
        except Exception as e:  # noqa: BLE001
            # Считать сбои и не говорить, какие именно, — это ровно та ошибка, за которую я
            # уже платил дважды: «ОГРН нет» вместо 429 и «страницу не дали» вместо пустого
            # кадра. Печатаем причину сразу.
            sch['сбоев'] += 1
            sch.setdefault('причины', {})
            klyuch = '%s: %s' % (e.__class__.__name__, str(e)[:90])
            sch['причины'][klyuch] = sch['причины'].get(klyuch, 0) + 1
            continue
        # ТОЛЬКО В ПУСТОЕ: у карточки может быть своя работа продавца
        pary = [('region', o.get('region')), ('adres', o.get('adres')),
                ('direktor', o.get('direktor')), ('sayt', o.get('sayt')),
                ('chistaya_pribyl', o.get('pribyl')), ('ssch', o.get('ssch')),
                ('vyruchka_rub', o.get('vyruchka')),
                ('telefony_checko', ' | '.join(o.get('telefony') or [])),
                ('pochty_checko', ' | '.join(o.get('pochty') or [])),
                ('istochnik_rekvizitov', 'checko.ru: ' + o['ssylka'])]
        for pole, znach in pary:
            if pole not in kolonki or znach in (None, '', 0):
                continue
            c.execute("update company set %s = ? where inn = ? and coalesce(%s,'') = ''"
                      % (pole, pole), (znach, inn))
            sch['записано полей'] += c.rowcount
        p.commit()
        f.write(json.dumps(o, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
        time.sleep(0.8)
    f.close()
    p.close()
    print(json.dumps(sch, ensure_ascii=False))


if __name__ == '__main__':
    main()
