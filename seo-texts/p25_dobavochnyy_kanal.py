# -*- coding: utf-8 -*-
"""Прямой стол технаря: искать НОМЕР С ДОБАВОЧНЫМ на сайте предприятия. Канал по итогу замера.

ПОЧЕМУ ЭТОТ КАНАЛ, А НЕ ПРОДОЛЖЕНИЕ ПРЕЖНИХ. Замер, повторённый четырьмя способами:

    людей с личным мобильным и первоисточником       13
    людей технического круга, подтверждённых сайтом  89
    В ОБОИХ МНОЖЕСТВАХ                                0

Ноль, а не «мало». Предприятие публикует мобильный тому, кто ОБЯЗАН принимать звонки снаружи:
пресс-службе, руководителю, контактному лицу по закупке. Главный инженер снаружи звонков не
принимает — у него приёмная и ДОБАВОЧНЫЙ. Дважды спрошенные 28 технических людей дали ноль
мобильных и на сайте, и на карточках закупок.

Значит буквальная мера ТЗ для технаря почти недостижима, а достижима другая вещь, которая
владельцу нужна ровно за тем же: ПРЯМОЙ СТОЛ. Городской плюс добавочный — это звонок сразу
нужному человеку, а не разговор с секретарём. У меня их 16, и все шестнадцать нашлись
попутно, ни один не искался нарочно.

ГДЕ ОНИ ЛЕЖАТ. На страницах контактов и структуры самого предприятия. Живой пример из моей же
выдачи: `kirovets-ptz.com/contacts/sluzhba-glavnogo-inzhenera/` — целая страница «Служба
главного инженера». Такие страницы есть у многих, и спрашивать их надо адресно:
`site:<домен> "главный инженер" телефон`.

ЧТО ЗАСЧИТЫВАЕТСЯ. Номер с добавочным, стоящий не дальше 400 знаков от слов должности, на
странице, которая проходит строгую приёмку. Добавочный обязателен: голый городской это
коммутатор, он у нас и так есть, и он ничего не решает.
"""
import collections
import csv
import importlib.util
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\_ops')
import _3s_chuzhaya_stranica as CH  # noqa: E402

POTOK = r'C:\sender\_ops\p25-dobavochnyy.jsonl'
BAZA = 'file:C:/seostat/data/p25.db?mode=ro'
SAYTY_FAJLY = (r'C:\sender\_ops\3s_p25_sayty_ot_1s.csv',
               r'C:\sender\_ops\3s_p25_sayty_2s.csv',
               r'C:\sender\_ops\3s_p25_sayty_2s_002.csv',
               r'C:\sender\_ops\3s_p25_sayty_iz_poiska.csv',
               r'C:\sender\_ops\3s_p25_sayty_iz_potokov.csv',
               r'C:\sender\_ops\3s_p25_sayty_iz_centro.csv')
KANDIDATY = (r'C:\sender\_ops\3s_lpr_obratnyy.py', r'C:\sender\_ops\_3s_lpr_obratnyy.py')

# ФОРМА ЗАПРОСА РЕШАЕТ ВСЁ, и первый прогон это доказал ценой 240 запросов и нуля.
#
# Я спрашивала `site:<домен> "главный инженер" телефон` — и получала снимки по 129-132 знака
# БЕЗ единого номера. Проверка прибора на странице, которую я видела своими глазами
# (`kirovets-ptz.com/contacts/sluzhba-glavnogo-inzhenera/`), показала причину: слово «телефон»
# в запросе не заставляет поисковик показать номер. А вот слово «доб» — заставляет:
#
#     site:kirovets-ptz.com "главный инженер" телефон  -> 0 номеров в снимках
#     site:kirovets-ptz.com контакты доб               -> +7-812-363-46-96 доб. 114
#                                                          +7-812-331-08-66 доб. 7619  (главный
#                                                                            конструктор)
#                                                          +7-812-363-46-96 доб. 106
#
# Это тот же урок, что дала должность в запросе: СНИМОК ВЫДАЧИ СЛЕДУЕТ ЗА ЗАПРОСОМ. Хочешь
# увидеть добавочный — назови «доб», а не «телефон». Ноль был мой, а не мира.
#
# ДОЛЖНОСТЬ БЕРЁТСЯ СО СТРАНИЦЫ, А НЕ ИЗ ЗАПРОСА. На таких сайтах раздел контактов разложен по
# службам, и должность стоит прямо в АДРЕСЕ: `/contacts/glavnyy-konstruktor/`,
# `/contacts/sluzhba-glavnogo-inzhenera/`. Это надёжнее слова в тексте и не требует отдельной
# проверки принадлежности.
FORMY = ('site:%s контакты доб', 'site:%s "доб." телефон', 'site:%s подразделения доб')
SLUZHBA_V_ADRESE = re.compile(
    r'glavn\w*[-_]?(?:inzhener|konstruktor|mehanik|energetik|tehnolog)|'
    r'sluzhba[-_]glavnogo|tehnicheskiy|glavnyy[-_]|energetik|mehanik|glavinzh', re.I)
SLUZHBA_V_TEKSTE = re.compile(
    r'главн\w*\s+(?:инженер|механик|энергетик|конструктор|технолог)|'
    r'служб\w*\s+главного|техническ\w+\s+(?:директор|служб|отдел)', re.I)
DOLZHNOSTI = ('главный инженер', 'главный механик', 'главный энергетик',
              'технический директор')
TEL = re.compile(r'(?:\+7|\b8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}\b')
DOB = re.compile(r'(?:доб(?:ав(?:очный)?)?\.?|вн(?:утр(?:енний)?)?\.?|ext\.?|#)\s*[:№]?\s*'
                 r'(\d{2,5})\b', re.I)
FIO = re.compile(r'\b([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ]\.\s?[А-ЯЁ]\.|[А-ЯЁ][а-яё]{2,}\s+'
                 r'[А-ЯЁ][а-яё]{3,}(?:ович|евич|ьевич|овна|евна|ьевна|ична))')


def _serp():
    for put in KANDIDATY:
        if os.path.exists(put):
            spec = importlib.util.spec_from_file_location('lpr', put)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m.serp
    raise SystemExit('модуля поиска нет')


def sayty():
    d = {}
    for p in SAYTY_FAJLY:
        if not os.path.exists(p):
            continue
        for r in csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';'):
            v = (r.get('ves') or '').strip()
            if v.isdigit() and int(v) < 2:
                continue
            if r.get('inn') and r.get('sayt'):
                d.setdefault(r['inn'], r['sayt'])
    return d


def main():
    import sqlite3
    serp = _serp()
    lim = int(sys.argv[sys.argv.index('--lim') + 1]) if '--lim' in sys.argv else 10 ** 9
    pot = int(sys.argv[sys.argv.index('--potokov') + 1]) if '--potokov' in sys.argv else 5
    st = sayty()
    b = sqlite3.connect(BAZA, uri=True)
    imena = {i: n for i, n in b.execute('select inn, coalesce(predpriyatie,"") from company')}
    mesta = {i: m for i, m in b.execute(
        'select inn, coalesce(mesto_po_summe, 9999) from company')}
    gotovo = set()
    if os.path.exists(POTOK):
        for ln in open(POTOK, encoding='utf-8'):
            try:
                z = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if not z.get('err'):
                gotovo.add(z['inn'])
    # Идём по деньгам: чем выше место по сумме покупок, тем дороже прямой стол.
    zad = sorted((i for i in st if i not in gotovo), key=lambda i: mesta.get(i, 9999))[:lim]
    print('сайтов %d, спрошено %d, к обходу %d' % (len(st), len(gotovo), len(zad)),
          file=sys.stderr, flush=True)

    f = open(POTOK, 'a', encoding='utf-8')
    lock = threading.Lock()
    sch = collections.Counter()

    def odin(inn):
        sayt = st[inn]
        nashli, err = [], ''
        for forma in FORMY:
            q = forma % sayt
            docs, e = serp(q)
            if e:
                err = e
                continue
            for d in docs:
                url = (d.get('url') or '').strip()
                t = ' '.join(v for k, v in d.items() if k != 'url' and isinstance(v, str))
                est, poch = CH.stranica_podtverzhdaet(url, sayt, imena.get(inn, ''), '',
                                                      strogo=True)
                if not est:
                    continue
                v_adrese = SLUZHBA_V_ADRESE.search(url)
                v_tekste = SLUZHBA_V_TEKSTE.search(t)
                if not (v_adrese or v_tekste):
                    continue
                sluzhba = (v_adrese.group(0) if v_adrese else v_tekste.group(0))
                for m in TEL.finditer(t):
                    md = DOB.search(t[m.end():m.end() + 40])
                    if not md:
                        continue
                    mf = FIO.search(t[max(0, m.start() - 300):m.start() + 300])
                    nashli.append({'dolzhnost': sluzhba,
                                   'otkuda_dolzhnost': ('адрес страницы' if v_adrese
                                                        else 'текст страницы'),
                                   'nomer': m.group(0),
                                   'dobavochnyy': md.group(1), 'ssylka': url,
                                   'pochemu': poch, 'zapros': q,
                                   'chelovek': mf.group(0) if mf else '',
                                   'citata': t[max(0, m.start() - 400):m.start() + 400]})
            if nashli:
                break
        return {'inn': inn, 'predpriyatie': imena.get(inn, ''), 'sayt': sayt,
                'err': err if not nashli else '', 'naydeno': nashli}

    with ThreadPoolExecutor(max_workers=pot) as ex:
        for r in ex.map(odin, zad):
            with lock:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
                if r['err']:
                    sch['сбой'] += 1
                elif r['naydeno']:
                    sch['ПРЯМОЙ СТОЛ НАЙДЕН'] += 1
                    if any(x['chelovek'] for x in r['naydeno']):
                        sch['  и человек назван'] += 1
                else:
                    sch['добавочного у технической службы нет'] += 1
    f.close()
    for k, v in sch.most_common():
        print('REC %s\t%d' % (k, v))
    print('ИТОГ ' + json.dumps({'спрошено предприятий': len(zad)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
