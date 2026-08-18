# -*- coding: utf-8 -*-
"""СЛОВАРЬ МАРОК из общих запросов по реестру — чтобы марку ставил СКРИПТ, а не провайдер.

ЗАЧЕМ. Провайдер разобрал 17 134 строки, где регулярка сдалась, и вынул марку у 7 091.
Это дорого и не воспроизводится: тот же корпус завтра надо просить заново. Но у нас на
руках теперь ДВА независимых источника обозначений — 19 818 марок регуляркой и 7 091
провайдером, — и из них можно построить словарь, по которому марка ставится СРАВНЕНИЕМ,
без единого вызова модели.

ЧТО ЭТО ДАЁТ, кроме экономии. Словарь — проверяемая вещь: у каждой марки видно, сколько
раз она встречена, у скольких РАЗНЫХ предприятий, к какому типу машины относится и по
какой ссылке это можно посмотреть. Марка, встреченная у одного ИНН один раз, и марка,
встреченная у сорока, — разные по надёжности, и счёт это показывает прямо.

ТРИ ВЫХОДА:
  PARK-SLOVAR-MAROK-2S.csv    марка · тип · встреч · ИНН · чем добыта · пример · ссылка
  PARK-SHABLONY-MAROK-2S.csv  форма обозначения (4ВМ10-100/8 → «Ц+БУКВЫ+Ц-Ц/Ц») со счётом:
                              по ней строится и ПРОВЕРЯЕТСЯ регулярка, а не по наитию
  PARK-SLOVA-PERED-MARKOJ-2S.csv  какое слово стоит ПЕРЕД обозначением и как часто:
                              «компрессор типа», «установка», «марки» — это якоря поиска

ЗАСЛОН ОТ МУСОРА. В обозначения лезут ГОСТ, ТУ, рег-номера, даты, диаметры. Отсеиваем не
на глаз: марка обязана встретиться либо НЕ МЕНЕЕ ЧЕМ У ДВУХ РАЗНЫХ ИНН, либо иметь форму,
которая уже подтверждена другими марками. Всё остальное уходит в отдельный файл сомнительных,
а не выбрасывается молча — счёт выброшенного тоже надо видеть.
"""
import collections
import csv
import io
import json
import os
import re
import sys

L = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engineers-lens')
SVOD = os.path.join(L, 'PARK-FAKTY-2S-SVOD.csv')
PROV = os.path.join(L, 'PARK-MARKA-PROVAJDER-2S.jsonl')
SLOVAR = os.path.join(L, 'PARK-SLOVAR-MAROK-2S.csv')
SHABLONY = os.path.join(L, 'PARK-SHABLONY-MAROK-2S.csv')
YAKORYA = os.path.join(L, 'PARK-SLOVA-PERED-MARKOJ-2S.csv')
SOMNITELNYE = os.path.join(L, 'PARK-MARKI-KANDIDATY-2S.csv')

MUSOR = re.compile(r'^(ГОСТ|ТУ|ФНП|РД|СНИП|СП|ПБ|ISO|DIN|ОСТ|EN)\b|^\d{2}\.\d{2}\.\d{4}$|'
                   r'^[А-Я]?\d{2}-\d{5}-\d{4}$|^\d+$|^№', re.I)
# ТРИ ЗАСЛОНА, КАЖДЫЙ ПОСТАВЛЕН ПО ЗАМЕРУ, А НЕ ПО ВПЕЧАТЛЕНИЮ (выборка из 12 глазами):
# 1) хвост после запятой: «ДЭН-45ШМ, С» — от «ДЭН-45ШМ, С ЗАВОДСКИМ № 306». 74 записи.
HVOST = re.compile(r',\s*(?:[А-ЯA-Z]\b|с\b|зав|инв|рег|тех|поз).*$', re.I)
# 2) марка, равная среде: «Осушитель СО2» — СО2 это то, что сушат, а не марка сушилки.
GAZ = re.compile(r'^(СО2|CO2|О2|O2|N2|СО|CO|NH3|Ar|Не|He|C2H4|H2|воздух)$', re.I)
# 3) технологическая ПОЗИЦИЯ: «Газодувка, тех. поз. К1402А» — К1402А это адрес машины в
#    схеме цеха, у соседнего завода под тем же кодом стоит другое. 653 записи из 4 814.
POZICIYA = re.compile(r'(?:тех\.?\s*)?поз(?:иция|\.)?\s*(?:№\s*)?$', re.I)
YAKOR = re.compile(r'([А-Яа-яA-Za-z]+(?:\s+[а-я]+)?)\s*$')


def klyuch_napisaniya(m):
    """Ключ склейки написаний одной марки: «305ВП 16/70» = «305ВП-16/70» = «305ВП16/70».

    ДЕСЯТИЧНЫЙ РАЗДЕЛИТЕЛЬ НЕ ТРОГАЕМ, и это не мелочь: первая версия ключа выбрасывала
    все не-буквы-цифры и слила **В-1,0 с В-10** — ресивер на 1 кубометр с ресивером на 10.
    Запятая и точка приводятся друг к другу, дефис и пробел схлопываются, остальное — как есть.
    """
    return re.sub(r'[\s-]+', '', m.upper().replace('Ё', 'Е').replace(',', '.'))


def forma(m):
    """Форма обозначения: цифры → Ц, кириллица → К, латиница → Л, разделители как есть.
    «4ВМ10-100/8» → «ЦКК Ц-Ц/Ц»; по форме видно, какие шаблоны реальны, а какие мусор."""
    out = []
    for ch in m:
        if ch.isdigit():
            t = 'Ц'
        elif 'А' <= ch.upper() <= 'Я' or ch in 'Ёё':
            t = 'К'
        elif ch.isalpha():
            t = 'Л'
        else:
            out.append(ch)
            continue
        if not out or out[-1] != t:
            out.append(t)
    return ''.join(out)


def main():
    vstrech = collections.Counter()
    innov = collections.defaultdict(set)
    tipy = collections.defaultdict(collections.Counter)
    chem = collections.defaultdict(collections.Counter)
    primer = {}
    yakorya = collections.Counter()

    def dobavit(marka, inn, tip, istochnik, citata, ssylka):
        m = ' '.join((marka or '').split()).strip(' ,.;:()«»"')
        m = HVOST.sub('', m).strip(' ,.;:-')
        if len(m) < 3 or len(m) > 28 or MUSOR.match(m) or GAZ.match(m):
            return
        # Позицию узнаём по тому, ЧТО СТОИТ ПЕРЕД НЕЙ в этой же цитате, а не по виду кода.
        if citata and m in citata and POZICIYA.search(citata[:citata.index(m)]):
            return
        vstrech[m] += 1
        if inn:
            innov[m].add(inn)
        if tip:
            tipy[m][tip] += 1
        chem[m][istochnik] += 1
        if m not in primer and citata:
            primer[m] = (citata[:200], ssylka)
        if citata and m in citata:
            do = citata[:citata.index(m)]
            y = YAKOR.search(do)
            if y:
                yakorya[y.group(1).lower().strip()] += 1

    for r in csv.DictReader(io.open(SVOD, encoding='utf-8-sig'), delimiter=';'):
        dobavit(r.get('marka_model'), r.get('inn'), r.get('tip'), 'регулярка',
                r.get('citata') or '', r.get('ssylka') or '')
    if os.path.exists(PROV):
        for ln in io.open(PROV, encoding='utf-8'):
            try:
                d = json.loads(ln)
            except json.JSONDecodeError:
                continue
            dobavit(d.get('marka'), d.get('inn'), d.get('tip_model'), 'провайдер',
                    d.get('citata') or '', d.get('ssylka') or '')

    # Формы, подтверждённые НЕЗАВИСИМО: форма считается настоящей, если её носят марки
    # не менее чем у трёх разных ИНН суммарно. Тогда одиночная марка редкой формы —
    # подозрительна, а одиночная марка ходовой формы — просто редкая машина.
    po_forme = collections.Counter()
    inn_po_forme = collections.defaultdict(set)
    for m in vstrech:
        po_forme[forma(m)] += vstrech[m]
        inn_po_forme[forma(m)] |= innov[m]
    horoshie_formy = {f for f in po_forme if len(inn_po_forme[f]) >= 3}

    stroki, somnit = [], []
    for m, n in vstrech.items():
        f = forma(m)
        row = {'marka': m, 'forma': f, 'vstrech': n, 'innov': len(innov[m]),
               'tip': (tipy[m].most_common(1)[0][0] if tipy[m] else ''),
               'chem_dobyta': '+'.join(sorted(chem[m])),
               'primer': primer.get(m, ('', ''))[0],
               'ssylka': primer.get(m, ('', ''))[1]}
        # В СЛОВАРЬ — ТОЛЬКО ПОДТВЕРЖДЁННОЕ ДВУМЯ РАЗНЫМИ ПРЕДПРИЯТИЯМИ. Форма сама по
        # себе не довод: замер показал 3 990 марок, пущенных по форме при одном ИНН, и
        # выборка глазами нашла среди них позиции, номера документов и обрезанные
        # обозначения. Одиночки уходят в кандидаты — не выброшены, но и не выданы за словарь.
        row['forma_hodovaya'] = 'да' if f in horoshie_formy else 'нет'
        (stroki if len(innov[m]) >= 2 else somnit).append(row)

    COLS = ['marka', 'klyuch', 'napisaniya', 'forma', 'forma_hodovaya', 'vstrech', 'innov',
            'tip', 'chem_dobyta', 'primer', 'ssylka']
    # Написания одной марки сводим в поле, а не в отдельные строки: скрипт ищет по ключу,
    # человек читает марку как её пишет реестр.
    po_klyuchu = collections.defaultdict(set)
    for r in stroki + somnit:
        po_klyuchu[klyuch_napisaniya(r['marka'])].add(r['marka'])
    for r in stroki + somnit:
        k = klyuch_napisaniya(r['marka'])
        r['klyuch'] = k
        r['napisaniya'] = ' | '.join(sorted(po_klyuchu[k]))
    for put, dannye in ((SLOVAR, stroki), (SOMNITELNYE, somnit)):
        with io.open(put, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=COLS, delimiter=';', extrasaction='ignore')
            w.writeheader()
            for r in sorted(dannye, key=lambda x: (-x['innov'], -x['vstrech'])):
                w.writerow(r)

    with io.open(SHABLONY, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['forma', 'marok', 'vstrech', 'innov', 'primery'])
        po_forme_marok = collections.Counter()
        primery_formy = collections.defaultdict(list)
        for m in vstrech:
            po_forme_marok[forma(m)] += 1
            if len(primery_formy[forma(m)]) < 4:
                primery_formy[forma(m)].append(m)
        for fo, k in po_forme_marok.most_common():
            w.writerow([fo, k, po_forme[fo], len(inn_po_forme[fo]),
                        ' | '.join(primery_formy[fo])])

    with io.open(YAKORYA, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['slovo_pered_markoj', 'skolko_raz'])
        for s, k in yakorya.most_common(200):
            w.writerow([s, k])

    print('марок всего %d | в словарь (2+ ИНН) %d | в кандидаты (1 ИНН) %d'
          % (len(vstrech), len(stroki), len(somnit)))
    print('форм обозначений %d, из них подтверждённых (3+ ИНН) %d'
          % (len(po_forme), len(horoshie_formy)))
    print('топ-10 словаря:')
    for r in sorted(stroki, key=lambda x: (-x['innov'], -x['vstrech']))[:10]:
        print('   %-16s %-12s встреч %4d у %3d ИНН  [%s]'
              % (r['marka'], r['forma'], r['vstrech'], r['innov'], r['chem_dobyta']))
    print('→', SLOVAR, '\n→', SHABLONY, '\n→', YAKORYA, '\n→', SOMNITELNYE)


if __name__ == '__main__':
    sys.exit(main())
