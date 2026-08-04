# -*- coding: utf-8 -*-
"""Сборка файла людей в формате 1-й сессии для заливки в базу user3.

ФОРМАТ ЗАДАН НЕ МНОЮ (`P25-TOCHKA-ZAPISI.md`):
    inn; chelovek; dolzhnost; podrazdelenie; telefon; pochta; rol; ssylka;
    data_nablyudeniya; citata
Напрямую в базу не пишет никто, включая 1-ю сессию: правило трёх исходов вставки
(завести / дописать номер в пустую клетку / записать вторым номером) должно жить в одном месте.

ЧТО ЗДЕСЬ ЧЕСТНО ПУСТО. Должности, подразделения и роли у площадок НЕТ — проверено по всем
92 полям карточки ЭТП ГПБ, полей вида position/post/dolzhnost нет вовсе. Пустая клетка здесь
означает «площадка этого не отдаёт», а не «мы не посмотрели». Заполнять их догадкой по слову
в предмете закупки нельзя: «контактное лицо по закупке подшипников» — это снабженец, а не
механик, и роль, поставленная так, переживёт все последующие проверки как настоящая.

ДАТА НАБЛЮДЕНИЯ — ДАТА ПРОЦЕДУРЫ. Прямое правило владельца: «дата процедуры и есть дата
актуализации контакта». Она берётся склейкой с файлом списков по (ИНН + номер процедуры) —
в файле людей её нет, там только номер.

ДЕДУП. Ключ — (ИНН, фамилия, 10 цифр номера). Один человек попадается в десятках процедур;
оставляем строку с САМОЙ СВЕЖЕЙ датой, потому что именно дата — то, ради чего строка нужна.
Фамилия, а не полное имя: у одного человека их бывает четыре написания.

Использование:
    python3 p25_otdat_lyudey.py
"""
import csv
import os
import re
import sys

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
LYUDI = os.path.join(L, 'P25-etpgpb-lica-s-kartochek.csv')
SPISKI = os.path.join(L, 'P25-etpgpb-po-kompaniyam.csv')
SAJTY = os.path.join(L, 'P25-LYUDI-S-SAJTOV.csv')
VYHOD = os.path.join(L, 'P25-LYUDI-2S.csv')
COLS = ['inn', 'chelovek', 'dolzhnost', 'podrazdelenie', 'telefon', 'pochta', 'rol',
        'ssylka', 'data_nablyudeniya', 'citata']

# Добавочный отрезается ДО чистки от знаков, иначе выходит `+849550593332424`.
DOB = re.compile(r'\s*(?:доб\.?|добавочный|вн\.?|ext\.?)\s*(\d{1,6})\s*$', re.I)


def chitat(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(p) else []


def familiya(s):
    ch = re.sub(r'[^А-ЯЁа-яё -]', ' ', s or '').split()
    return ch[0].lower() if ch else ''


def desyat(t):
    c = re.sub(r'\D', '', t or '')
    if len(c) == 11 and c[0] in '78':
        c = c[1:]
    return c if len(c) == 10 else ''


def klyuch_daty(d):
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', d or '')
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (0, 0, 0)


def main():
    spiski = chitat(SPISKI)
    # (ИНН, номер процедуры) → дата. Ключ такой же, как у правила «один документ — один факт».
    daty = {}
    for r in spiski:
        n = (r.get('nomer') or '').strip()
        if n:
            daty[(r.get('inn', ''), n)] = (r.get('data') or '').strip()

    lyudi = chitat(LYUDI)
    luchshee = {}
    bez_familii = bez_nomera = 0
    for r in lyudi:
        imya = (r.get('chelovek') or '').strip()
        f = familiya(imya)
        if not f:
            bez_familii += 1
            continue
        # `mobilnyy` — ФЛАГ («да»), А НЕ НОМЕР. Первая версия читала его как телефон, и в
        # 23 строках из 120 в поле телефона уехало бы слово «да». Мобильность считается по
        # самому номеру, а не по чужой пометке: 11 цифр с 7/8 и второй 9, либо 10 с первой 9.
        syroy = (r.get('telefon') or '').strip()
        m = DOB.search(syroy)
        dobav = m.group(1) if m else ''
        nomer_ch = DOB.sub('', syroy).strip()
        d10 = desyat(nomer_ch)
        if not d10 and not (r.get('pochta') or '').strip():
            bez_nomera += 1
            continue
        proc = (r.get('nomer') or '').strip()
        data = daty.get((r.get('inn', ''), proc), '')
        k = (r.get('inn', ''), f, d10)
        citata = f'карточка закупки {proc}: контактное лицо «{imya}»'
        if nomer_ch:
            citata += f', телефон «{nomer_ch}»'
        if dobav:
            citata += f', добавочный {dobav}'
        stroka = {
            'inn': r.get('inn', ''),
            'chelovek': imya,
            'dolzhnost': '',        # площадка не отдаёт — см. шапку модуля
            'podrazdelenie': '',
            'telefon': nomer_ch,
            'pochta': (r.get('pochta') or '').strip(),
            'rol': '',
            'ssylka': (r.get('ssylka') or '').strip(),
            'data_nablyudeniya': data,
            'citata': citata,
        }
        if k not in luchshee or klyuch_daty(data) > klyuch_daty(luchshee[k]['data_nablyudeniya']):
            luchshee[k] = stroka

    # ВТОРОЙ ИСТОЧНИК — САЙТЫ ПРЕДПРИЯТИЙ. У него всё наоборот, чем у площадок: должность и
    # подразделение есть почти всегда, телефон почти никогда (страницы руководства прямых
    # номеров не публикуют). Поэтому он не заменяет площадки, а дополняет их — и склеивается
    # тем же ключом (ИНН, фамилия, 10 цифр номера). Человек без номера имеет пустой ключ по
    # номеру и с телефонной записью того же человека не сольётся: это намеренно, решение о
    # склейке принимает оп по правилу трёх исходов, а не я догадкой.
    s_sajtov = 0
    for r in chitat(SAJTY):
        imya = (r.get('chelovek') or '').strip()
        f2 = familiya(imya)
        if not f2:
            continue
        nomer_ch = (r.get('telefon') or '').strip()
        d10 = desyat(nomer_ch)
        stranica = (r.get('stranica') or '').strip()
        k = (r.get('inn', ''), f2, d10)
        stroka = {
            'inn': r.get('inn', ''),
            'chelovek': imya,
            'dolzhnost': (r.get('dolzhnost') or '').strip(),
            'podrazdelenie': (r.get('podrazdelenie') or '').strip(),
            'telefon': nomer_ch,
            'pochta': (r.get('pochta') or '').strip(),
            'rol': '',
            'ssylka': stranica,
            # Даты у страницы сайта НЕТ, и выдумывать «сегодня» нельзя: сегодня — это когда мы
            # посмотрели, а не когда сведения верны. Пустая клетка честнее.
            'data_nablyudeniya': '',
            'citata': f'страница сайта: «{imya}»'
                      + (f', {r.get("dolzhnost")}' if r.get('dolzhnost') else '')
                      + (f', телефон «{nomer_ch}»' if nomer_ch else ''),
        }
        if k not in luchshee:
            luchshee[k] = stroka
            s_sajtov += 1

    rows = sorted(luchshee.values(), key=lambda x: (x['inn'], x['chelovek']))

    # ИМЯ НА КАЖДЫЙ ЗАХОД СВОЁ, А НЕ ОДНО НА ВСЕ. Просьба 3-й сессии, и она подкреплена
    # потерей: их файл под постоянным именем сменился между двумя заливками соседа, и сорок
    # строк середины не попали в базу и на дропе их больше нет. Приёмка идёт по сторожу раз
    # в 25 минут — любая перезапись внутри окна теряет то, что не успело влиться.
    # Общий `P25-LYUDI-2S.csv` тоже пишется: по нему удобно смотреть текущее целое.
    nomer = 1
    while os.path.exists(os.path.join(L, f'P25-LYUDI-2S-{nomer:03d}.csv')):
        nomer += 1
    puti = [VYHOD, os.path.join(L, f'P25-LYUDI-2S-{nomer:03d}.csv')]
    for put in puti:
        with open(put, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=COLS, delimiter=';', extrasaction='ignore')
            w.writeheader()
            w.writerows(rows)

    mob = sum(1 for x in rows if desyat(x['telefon'])[:1] == '9')
    s_datoy = sum(1 for x in rows if x['data_nablyudeniya'])
    print(f'вход: {len(lyudi)} строк карточек', file=sys.stderr)
    print(f'  без разбираемой фамилии: {bez_familii}', file=sys.stderr)
    print(f'  без номера и без почты:  {bez_nomera}', file=sys.stderr)
    print(f'ВЫХОД: {len(rows)} человек на {len({x["inn"] for x in rows})} предприятиях',
          file=sys.stderr)
    print(f'  с личным мобильным: {mob}', file=sys.stderr)
    print(f'  с датой наблюдения: {s_datoy} (дата процедуры)', file=sys.stderr)
    print(f'  добавлено с сайтов: {s_sajtov} (у них должность есть, даты нет)', file=sys.stderr)
    print(f'  с должностью: {sum(1 for x in rows if x["dolzhnost"])}', file=sys.stderr)
    for put in puti:
        print(f'→ {put}', file=sys.stderr)


if __name__ == '__main__':
    main()
