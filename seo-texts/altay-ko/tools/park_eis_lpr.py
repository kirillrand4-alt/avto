# -*- coding: utf-8 -*-
"""ЛПР С КАРТОЧКИ ЗАКУПКИ ЕИС для базы ПАРК: имя, ДОЛЖНОСТЬ, прямой телефон, почта.

ЗАЧЕМ ИМЕННО ЭТО И ИМЕННО СЕЙЧАС. Глазами проверил 25 случайных ссылок базы (пункт 5
владельца). Ссылки ведут на доказательство все 25 из 25 — но роль контакта чаще не наша:
гинеколог краевой больницы, «Ольга» из отдела кадров, бухгалтерия. Замер по всему файлу:
3 062 строки контактов, а человек НАШЕЙ роли — 49. Дыра не в ссылках, а в РОЛИ.

Сайт предприятия должности почти не даёт, площадки не дают вовсе (проверено на ЭТП ГПБ:
имя есть, должностных слов на странице ноль). Единственный канал, где заказчик САМ пишет
должность контактного лица, — карточка закупки ЕИС:

    «Ответственное должностное лицо по вопросам разъяснения ТЕХНИЧЕСКОГО ЗАДАНИЯ:
     Начальник Управления … – Прокофьев Михаил Юрьевич, тел. (812) 326-52-73 доб. 69»

ОТКУДА НОМЕРА. `PARK-EIS-ZAKAZCHIKI-3S.jsonl` — 544 закупки на 343 ИНН, собрала 3-я сессия
по компрессорным словам. Своего обхода ЕИС не пишу: правило смены — «площадку гонит тот, у
кого её скрипт», а разбор карточки на людей мой (`p25_eis_kontakty.razobrat`). Беру их
номера, отдаю обратно людей — это сложение, а не дубль.

ЧЕСТНАЯ ГРАНИЦА. 334 из 343 ИНН в базе машин ОТСУТСТВУЮТ: закупка компрессора — это
доказательство класса 2 (оплачено и датировано процедурой), а не надзорная запись о машине
в эксплуатации. Поэтому строки помечаются `klass=2` и НЕ выдаются как «у них стоит».

Использование:
    python3 park_eis_lpr.py [--predel 0] [--parallel 3]
"""
import argparse
import csv
import io
import json
import re
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import p25_eis_kontakty as E
import p25_hodok as hodok

BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
VHOD = os.path.join(L, 'PARK-EIS-ZAKAZCHIKI-3S.jsonl')
VYHOD = os.path.join(L, 'PARK-EIS-LPR-2S.csv')
COLS = ['inn', 'predpriyatie', 'zakazchik_realnyy', 'chey_kontakt', 'chelovek', 'dolzhnost',
        'telefon', 'dobavochnyy', 'pochta', 'po_voprosam', 'nomer_procedury', 'predmet',
        'klass', 'sila', 'ssylka', 'kak', 'citata']

# ПОЙМАНО НА ЧЕТЫРЁХ ПЕРВЫХ КАРТОЧКАХ, ДО ПОЛНОГО ПРОГОНА. В строке 3-й сессии поле
# `zakazchik` — это тот, кто ОБЪЯВИЛ процедуру, а он часто УПОЛНОМОЧЕННЫЙ ОРГАН:
# «Комитет государственного заказа Хабаровского края», «Министерство по регулированию
# контрактных отношений». Машину получит не он. Настоящего заказчика карточка называет
# отдельно: «Требования заказчика «КГБУЗ «Краевая клиническая больница»…»» — и почта
# на карточке (resurskkb1@mail.ru) тоже его, а не министерства.
# Это ТОТ ЖЕ класс ошибки, что `inn` против `inn_eo` в ЭПБ: база выглядела бы настоящей и
# была бы про закупочные комитеты. Пишем обоих и помечаем, чей контакт.
ZAKAZCHIK = re.compile(r'[Тт]ребовани\w+\s+заказчика\s*[«"\']([^»"\']{5,220})')
ORGAN = re.compile(r'уполномоченн\w+\s+(?:орган|учреждени)|комитет\s+государственного\s+заказа|'
                   r'управлени\w+\s+государственного\s+заказа|министерство\s+по\s+регулированию',
                   re.I)

zamok = threading.Lock()
schet = {'карточек': 0, 'людей': 0, 'пусто': 0, 'не дошли': 0}


def sdelano():
    if not os.path.exists(VYHOD):
        return set()
    with io.open(VYHOD, encoding='utf-8-sig') as f:
        return set(r['nomer_procedury'] for r in csv.DictReader(f, delimiter=';'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--predel', type=int, default=0)
    ap.add_argument('--parallel', type=int, default=3)
    a = ap.parse_args()

    zadachi = []
    vidal = set()
    for l in io.open(VHOD, encoding='utf-8'):
        try:
            d = json.loads(l)
        except Exception:
            continue
        n = (d.get('nomer') or '').strip()
        if n and n not in vidal:
            vidal.add(n)
            zadachi.append(d)
    est = sdelano()
    zadachi = [d for d in zadachi if d['nomer'] not in est]
    if a.predel:
        zadachi = zadachi[:a.predel]
    print('карточек к обходу: %d (уже сделано %d)' % (len(zadachi), len(est)))

    novyy = not os.path.exists(VYHOD)
    f = io.open(VYHOD, 'a', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=COLS, delimiter=';', extrasaction='ignore')
    if novyy:
        w.writeheader()

    def odna(d):
        nomer = d['nomer']
        ssylka = E.adres_po_nomeru(nomer)
        res, kak, err = hodok.vzyat(ssylka, E.SKRIPT, after_ms=5000, timeout=600)
        if res is None or kak == hodok.NE_OTKRYLSYA:
            with zamok:
                schet['не дошли'] += 1
            return
        # СТРАНИЦА ОБЯЗАНА НАЗВАТЬ СЕБЯ. Заслон оплачен сменой: ЕИС писал «обойдено» на
        # 412 заглушках из 670. `chto` != 'карточка' — это не карточка, и людей там нет.
        chto = res.get('chto') or 'карточка'
        if chto != 'карточка':
            with zamok:
                schet['не дошли'] += 1
            return
        tekst = res.get('tekst') or ''
        m = ZAKAZCHIK.search(tekst)
        realnyy = ' '.join(m.group(1).split()) if m else ''
        obyavil = d.get('zakazchik', '')
        if realnyy and realnyy.lower()[:25] not in obyavil.lower():
            chey = 'уполномоченный орган, машина у заказчика'
        elif ORGAN.search(obyavil):
            chey = 'уполномоченный орган, заказчик не назван'
        else:
            chey = 'сам заказчик'
        lyudi = E.razobrat(tekst, nomer, ssylka)
        with zamok:
            schet['карточек'] += 1
            if not lyudi:
                schet['пусто'] += 1
            for c in lyudi:
                c.update({'inn': d.get('inn', ''), 'predpriyatie': d.get('zakazchik', ''),
                          'predmet': (d.get('predmet') or '')[:200], 'klass': '2',
                          'sila': '5', 'kak': kak, 'ssylka': ssylka,
                          'zakazchik_realnyy': realnyy, 'chey_kontakt': chey})
                w.writerow(c)
                schet['людей'] += 1
            f.flush()
            if schet['карточек'] % 25 == 0:
                print('  ', dict(schet), flush=True)

    with ThreadPoolExecutor(max_workers=a.parallel) as p:
        list(p.map(odna, zadachi))
    f.close()
    print('ИТОГ:', dict(schet), '→', VYHOD)


if __name__ == '__main__':
    main()
