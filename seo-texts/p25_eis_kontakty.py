# -*- coding: utf-8 -*-
"""ЕИС (zakupki.gov.ru): ДОЛЖНОСТЬ, полное имя и прямой телефон с карточки закупки.

ЗАЧЕМ. Всю смену мера ТЗ — «технический ЛПР с личным мобильным» — стояла на нуле при сотне
личных мобильных в базе. Причина измерена: **должностей не даёт ни одна площадка**. Проверено
на живой карточке ЭТП ГПБ: имя контактного лица есть, должностных слов на всей странице ноль.
Должность приходила только с сайта предприятия, а сайт находится далеко не у всех.

ЧТО ОТДАЁТ ЕИС. На карточке закупки лежит то, чего нет ни у кого, и в открытом доступе:

    Ответственное должностное лицо | Харламова Е. В.
    Адрес электронной почты        | Harlamova_EV@vodokanal.spb.ru
    Номер контактного телефона     | 7-812-...

и, что ценнее, СВОБОДНЫЙ ТЕКСТ с полной должностью, полным именем и прямым номером:

    «Ответственное должностное лицо по вопросам разъяснения ТЕХНИЧЕСКОГО ЗАДАНИЯ:
     Начальник Управления заказчика строительства бюджетных объектов – Прокофьев Михаил
     Юрьевич, ... контактный телефон/факс: (812) 326-52-73, доб. 69,
     адрес электронной почты: Prokofyev_MY@vodokanal.spb.ru»

«По вопросам разъяснения технического задания» — это ПРЯМО наш круг ЛПР, названный самим
заказчиком. И это первоисточник в самом сильном смысле: официальный сайт госзакупок.

ОБЪЁМ. Номеров ЕИС у нас 70 830 только по Сбербанк-АСТ, все 19-значные (44-ФЗ).

СЕРТИФИКАТ. `zakupki.gov.ru` на корне НУЦ Минцифры: без второго захода браузер отдаёт
«Your connection is not private», и первый пробник записал это как «страницы нет». Ходок
`p25_hodok` разводит это сам и запоминает хост, чтобы не удваивать 70 тысяч запросов.

ЧЕГО МОДУЛЬ НЕ ДЕЛАЕТ. Не решает роль: он отдаёт должность дословно, как её написал заказчик.
Роль ставится на сборке, по подразделению, общими правилами — и там же работают заслоны
«не человек» и «зона не наша».

Использование:
    python3 p25_eis_kontakty.py --predel 40 --na-predpriyatie 6 --parallel 3
"""
import csv
import os
import re
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import p25_hodok as hodok

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
OCHERED = os.path.join(L, 'P25-OCHERED.csv')
VYHOD = os.path.join(L, 'P25-EIS-KONTAKTY.csv')
KARTA = os.path.join(L, 'P25-eis-zhurnal.csv')
COLS = ['inn', 'predpriyatie', 'chelovek', 'dolzhnost', 'telefon', 'dobavochnyy', 'pochta',
        'po_voprosam', 'nomer_procedury', 'data', 'ssylka', 'kak', 'citata']
ZHCOLS = ['inn', 'nomer', 'lyudej', 'znakov', 'kak', 'pochemu']

# Откуда берутся номера. Все файлы площадок, где номер 19-значный (44-ФЗ).
ISTOCHNIKI = ['P25-sberast-po-kompaniyam.csv', 'P25-etpgpb-po-kompaniyam.csv',
              'P25-roseltorg-po-kompaniyam.csv', 'P25-tektorg-po-kompaniyam.csv',
              'P25-portal-po-kompaniyam-inn.csv', 'P25-rts-po-kompaniyam.csv']

ADRES = 'https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber={}'
# ДВА ЗАКОНА — ДВА АДРЕСА, И ЭТО НЕ МЕЛОЧЬ. Первая версия ходила только по 44-ФЗ и брала
# номера длиной 19. Пересчёт по длине показал: 19-значных у нас 8 442 на ДВАДЦАТИ
# предприятиях, а 11-значных — 4 480 на ВОСЕМНАДЦАТИ других. Одиннадцать знаков это 223-ФЗ,
# у него свой раздел ЕИС и своё извещение, и контактное лицо там названо так же. То есть
# половина канала просто не спрашивалась: не потому что данных нет, а потому что модуль знал
# один адрес из двух.
ADRES_223 = ('https://zakupki.gov.ru/223/purchase/public/purchase/info/common-info.html'
             '?regNumber={}')


def adres_po_nomeru(n):
    """Длина номера называет закон: 19 знаков — 44-ФЗ, 11 — 223-ФЗ. Признак дешёвый и
    надёжнее любой пометки площадки: у Росэлторга в одном файле лежат оба вида."""
    return ADRES_223.format(n) if len(n) == 11 else ADRES.format(n)

# СТРАНИЦА КАРТОЧКИ ИЛИ НЕ КАРТОЧКА — РЕШАЕТ САМА СТРАНИЦА. Журнал записал «обойдено» на 243
# карточки 223-ФЗ подряд, людей 0, и у ВСЕХ длина текста ровно 2452 знака. Двести сорок три
# разные закупки не могут весить одинаково — это была одна и та же страница: адрес уводил на
# ГЛАВНУЮ ЕИС («Официальный сайт Единой информационной системы... Мой регион: Не выбран»).
# Часть 19-значных отдавала 67 знаков — «Запрашиваемая страница не существует». И то и другое
# записывалось успехом, то есть эти номера больше никогда бы не переспросили.
SKRIPT = r"""
window.__RES = (async () => {
  await new Promise(r => setTimeout(r, 4500));
  const t = document.body ? document.body.innerText : '';
  let chto = 'карточка';
  if (/Запрашиваемая страница не существует/i.test(t)) chto = 'страницы нет';
  else if (t.length < 400) chto = 'страница пустая';
  else if (!/Заказчик|Контактн|Организатор|Извещени/i.test(t)) chto = 'увело на главную ЕИС';
  return JSON.stringify({origin: location.origin, dlina: t.length, chto: chto,
                         tekst: t.slice(0, 60000)});
})();
"""

FIO_POLNOE = r'[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё\-]{4,}'
FIO_KRATKOE = r'[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.'

# СВОБОДНЫЙ ТЕКСТ: «<по вопросам чего>: <Должность> – <Фамилия Имя Отчество>, ...».
# Тире бывает любым из трёх: длинное, среднее, дефис.
SVOBODNO = re.compile(
    r'(?:Ответственн\w+\s+должностн\w+\s+лиц\w*|Контактн\w+\s+лиц\w*)'
    r'(?P<vopros>[^:]{0,120})?:\s*'
    r'(?P<dolzh>[^–—\-\n]{5,160}?)\s*[–—-]\s*'
    r'(?P<fio>' + FIO_POLNOE + r')', re.I)

# СТРУКТУРНЫЙ БЛОК: «Ответственное должностное лицо | Харламова Е. В.»
STRUKTURNO = re.compile(
    r'Ответственн\w+\s+должностн\w+\s+лиц\w*\s*\n\s*(?P<fio>' + FIO_POLNOE
    + r'|' + FIO_KRATKOE + r')', re.I)

TEL = re.compile(r'(?:\+?7|8)?[\s\-()]*\(?\d{3,5}\)?[\s\-()]*\d{2,3}[\s\-]?\d{2}[\s\-]?\d{2}')
DOB = re.compile(r'доб(?:ав\w*)?\.?\s*(\d{1,6})', re.I)
# ЕИС ПИШЕТ ДОБАВОЧНЫЙ ЧЕРЕЗ ДЕФИС, БЕЗ СЛОВА. Поймано владельцем на живой карточке ОАК:
# «Номер контактного телефона: 7-495-9261420-8559». Правило «резать по доб|вн|ext» здесь не
# срабатывает вовсе, номер обрезается до 7-495-9261420, и продавец звонит на коммутатор — а
# 8559 и есть то, что делает контакт рабочим. Признак: после полного номера (10–11 цифр)
# стоит дефис и ещё 3–5 цифр. Это не часть номера: в России их столько не бывает.
DOB_DEFIS = re.compile(r'(?<=\d)-(\d{3,5})\s*$')


def razdelit_nomer(syroy):
    """«7-495-9261420-8559» → («7-495-9261420», «8559»). Слово «доб» проверяется первым:
    оно надёжнее, дефис — запасной признак и только на хвосте строки."""
    s = (syroy or '').strip()
    m = DOB.search(s)
    if m:
        return DOB.sub('', s).strip(' ,;-'), m.group(1)
    m = DOB_DEFIS.search(s)
    if m:
        cifry = re.sub(r'\D', '', s[:m.start()])
        if 10 <= len(cifry) <= 11:      # база уже полный номер — хвост добавочный
            return s[:m.start()].strip(), m.group(1)
    return s, ''
POCHTA = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


def chitat(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(p) else []


def okno(tekst, poz, vpered=420):
    """Кусок текста ПОСЛЕ имени: телефон и почта человека стоят там, а не до него."""
    return tekst[poz:poz + vpered]


def razobrat(tekst, nomer, ssylka):
    """Текст карточки ЕИС → люди. Каждому — своя цитата из этого же текста."""
    lyudi, vidno = [], set()

    for m in SVOBODNO.finditer(tekst):
        fio = m.group('fio').strip()
        if fio in vidno:
            continue
        hvost = okno(tekst, m.end())
        tel = TEL.search(hvost)
        dob = DOB.search(hvost)
        poc = POCHTA.search(hvost)
        vopros = (m.group('vopros') or '').strip(' ,;')
        vidno.add(fio)
        lyudi.append({
            'chelovek': fio,
            'dolzhnost': ' '.join(m.group('dolzh').split())[:160],
            'telefon': razdelit_nomer(tel.group(0) if tel else '')[0],
            'dobavochnyy': (dob.group(1) if dob
                            else razdelit_nomer(tel.group(0) if tel else '')[1]),
            'pochta': (poc.group(0) if poc else ''),
            'po_voprosam': vopros[:120],
            'citata': ' '.join(tekst[max(0, m.start()):m.end() + 220].split())[:400],
        })

    for m in STRUKTURNO.finditer(tekst):
        fio = m.group('fio').strip()
        if fio in vidno:
            continue
        hvost = okno(tekst, m.end())
        tel = TEL.search(hvost)
        poc = POCHTA.search(hvost)
        dob = DOB.search(hvost)
        vidno.add(fio)
        lyudi.append({
            'chelovek': fio,
            # Должности в структурном блоке НЕТ — это отдельный факт, а не пустая клетка.
            'dolzhnost': '',
            'telefon': razdelit_nomer(tel.group(0) if tel else '')[0],
            'dobavochnyy': (dob.group(1) if dob
                            else razdelit_nomer(tel.group(0) if tel else '')[1]),
            'pochta': (poc.group(0) if poc else ''),
            'po_voprosam': 'ответственное должностное лицо заказчика',
            'citata': ' '.join(tekst[max(0, m.start() - 60):m.end() + 220].split())[:400],
        })
    return lyudi


def main():
    parallel = dovod('--parallel', 3)
    na_predpriyatie = dovod('--na-predpriyatie', 6)
    predel = dovod('--predel', 10 ** 9)

    och = {r['inn']: r for r in chitat(OCHERED)}
    po_inn = defaultdict(dict)
    for f in ISTOCHNIKI:
        for r in chitat(os.path.join(L, f)):
            n = (r.get('nomer') or '').strip()
            # ЗАКОН 2005 ГОДА НЕ СПРАШИВАЕМ ВОВСЕ. Замер по журналу, признак безошибочный:
            #     44-ФЗ      217 карточек → 204 человека, пустых  0
            #     площадки   126 карточек →  47 человек,  пустых  0
            #     ФЗ-94       64 карточки →   0 человек,  пустых 64
            # Извещений ФЗ-94 в нынешнем ЕИС нет: страница отдаёт 67 знаков «Запрашиваемая
            # страница не существует». Ходить туда — тратить слот раннера на заведомо пустую
            # страницу и писать «обойдено» там, где обходить нечего.
            if '94' in (r.get('istochnik') or ''):
                continue
            if r.get('inn') in och and n.isdigit() and len(n) in (19, 11):
                po_inn[r['inn']].setdefault(n, (r.get('data') or ''))

    proydeno = {r['nomer'] for r in chitat(KARTA)}
    zadanie = []
    for inn in sorted(po_inn, key=lambda i: int(och[i].get('mesto') or 10 ** 9)):
        # СВЕЖИЕ ВПЕРЁД: дата процедуры и есть дата актуализации контакта.
        nomera = sorted(po_inn[inn].items(), key=lambda t: t[1], reverse=True)
        vzyato = 0
        for n, d in nomera:
            if n in proydeno:
                continue
            zadanie.append((inn, n, d))
            vzyato += 1
            if vzyato >= na_predpriyatie:
                break
    zadanie = zadanie[:predel]
    if not zadanie:
        print('целей нет', file=sys.stderr)
        return

    import predel_rannera
    predel_rannera.preduprezhdenie(parallel)
    print(f'карточек ЕИС к обходу: {len(zadanie)} по {len({i for i, _, _ in zadanie})} '
          f'предприятиям (пройдено {len(proydeno)})', file=sys.stderr)

    fv, novyy_v, per_v, otl_v = hodok.dopisyvat(VYHOD, COLS)
    fk, novyy_k, per_k, otl_k = hodok.dopisyvat(KARTA, ZHCOLS)
    wv = csv.DictWriter(fv, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy_v:
        wv.writeheader()
    wk = csv.DictWriter(fk, fieldnames=ZHCOLS, delimiter=';', extrasaction='ignore')
    if novyy_k:
        wk.writeheader()

    sch = {'карточек': 0, 'людей': 0, 'с должностью': 0, 'с телефоном': 0, 'сбоев': 0}
    lock = threading.Lock()

    def odna(z):
        inn, n, d = z
        ssylka = adres_po_nomeru(n)
        res, kak, err = hodok.vzyat(ssylka, SKRIPT, after_ms=5000, timeout=600)
        return z, res, kak, err

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        for k, (z, res, kak, err) in enumerate(pool.map(odna, zadanie), 1):
            inn, n, d = z
            with lock:
                if res is None or kak == hodok.NE_OTKRYLSYA:
                    sch['сбоев'] += 1
                    print(f'  СБОЙ {n}: {err[:90]}', file=sys.stderr, flush=True)
                    continue
                tekst = res.get('tekst') or ''
                lyudi = razobrat(tekst, n, adres_po_nomeru(n))
                sch['карточек'] += 1
                for ch in lyudi:
                    sch['людей'] += 1
                    if ch['dolzhnost']:
                        sch['с должностью'] += 1
                    if ch['telefon']:
                        sch['с телефоном'] += 1
                    wv.writerow(dict(ch, inn=inn,
                                     predpriyatie=och.get(inn, {}).get('predpriyatie', ''),
                                     nomer_procedury=n, data=d,
                                     ssylka=adres_po_nomeru(n), kak=kak))
                # ЧТО ЭТО БЫЛО ЗА СТРАНИЦА — ПИШЕМ ЕЁ СОБСТВЕННЫЙ ОТВЕТ. Скрипт научился
                # различать карточку, «страницы нет», пустую и главную ЕИС ещё в прошлый
                # заход — а запись осталась прежней, и журнал по-прежнему говорил «обойдено»
                # на всё подряд. Починка знала ответ и не доносила его: половина работы хуже,
                # чем никакой, потому что выглядит как целая.
                chto = res.get('chto') or 'карточка'
                wk.writerow({'inn': inn, 'nomer': n, 'lyudej': len(lyudi),
                             'znakov': res.get('dlina') or 0, 'kak': kak,
                             'pochemu': 'обойдено' if chto == 'карточка' else chto})
                fv.flush()
                fk.flush()
                if k % 5 == 0 or k == len(zadanie):
                    print(f'  {k}/{len(zadanie)}: ' + ', '.join(f'{a} {b}' for a, b in sch.items()),
                          file=sys.stderr, flush=True)
    fv.close()
    fk.close()
    print(f'готово: {sch}\n→ {VYHOD}', file=sys.stderr)


if __name__ == '__main__':
    main()
