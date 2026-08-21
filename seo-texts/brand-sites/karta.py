#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Карта моделей и распределения вместо диапазонов.

    python3 karta.py --export <bitrix.csv> [--out karta.json]

ЗАЧЕМ. Разбор владельца 21.08 дал пять находок, и все пять - один дефект:
ТЗ требует вычислений, которых переданные данные не поддерживают, а модель
закрывает разрыв правдоподобным числом.

  подбор:   «расход 12 000 л/мин + 10 бар -> подходящая мощность» - из этих
            двух величин мощность НЕ ВЫВОДИТСЯ. И подача зависит от давления:
            машина на 12 400 л/мин при 7 бар при 13 бар даёт заметно меньше.
  сегменты: «3-15 кВт -> сколько позиций» - в payload лежит только общее
            число 386 и границы 3-500. Распределение из них не получить.
  ресивер:  правило «10-20% минутной производительности» даёт 7000-14 000 л,
            а встроенные ресиверы в линейке 150-500. Разрыв в двадцать раз,
            и он необъясним, пока не видно, что встроенный привязан
            к МАШИНЕ, а не к сети.
  цена:     ценовые полки требуют распределения, а не min-max.

Диапазон - это два числа с концов линейки, и они принадлежат РАЗНЫМ
машинам. Любая арифметика между ними даёт несуществующую машину. Поэтому
здесь считаются РАСПРЕДЕЛЕНИЯ и хранится КАРТА КАРТОЧЕК: модель, мощность,
давление, подача, ресивер, цена - по каждой позиции отдельно.

ДЕДУПЛИКАЦИЯ ОБЯЗАТЕЛЬНА. Битрикс дублирует строку товара на каждое
множественное значение свойства: 600 738 строк на 27 477 товаров, в среднем
x22. Скрипт, читающий построчно, завышает все счётчики двадцатикратно -
на этом я уже обжёгся с правилами маркировки.
"""
import argparse, collections, csv, json, os, statistics, sys

csv.field_size_limit(10 ** 7)
DIR = os.path.dirname(os.path.abspath(__file__))

KOL = {
    'imya': 'IE_NAME', 'brend': 'IP_PROP22553', 'kvt': 'IP_PROP22562',
    'bar': 'IP_PROP22573', 'lmin': 'IP_PROP22571', 'resiver_l': 'IP_PROP22564',
    'resiver': 'IP_PROP22574', 'osushitel': 'IP_PROP22565',
    'chastotnik': 'IP_PROP22586', 'privod': 'IP_PROP22601',
    'smazka': 'IP_PROP22583', 'seriya': 'IP_PROP22576',
    'tsena': 'IP_PROP22704', 'gruppa': 'IP_PROP22602', 'tip': 'IP_PROP22892',
}
SAYT = {
    'abac': 'abac-kompressor.ru', 'atlas copco': 'ac-kompressor.ru',
    'berg': 'berg-kompressor.ru', 'cross air': 'crossair-compressor.ru',
    'dali': 'dali-kompressor.ru', 'ekomak': 'ekomak-kompressor.com',
    'enger': 'enger-air.ru', 'fini': 'fini-compressor.com',
    'ironmac': 'ironmac-compressor.com', 'kraftmann': 'kraftmann-kompressor.com',
    'remeza': 'remeza-kompressor.ru', 'зиф': 'zif-kompressor.ru',
}
# Полки мощности. Границы не круглые ради красоты, а по тому, как делится
# рынок: до 15 кВт мастерская и сервис, 18-90 цех, 110-250 производство,
# выше - непрерывка и каскады.
POLKI = [(0, 15), (15, 90), (90, 250), (250, 100000)]
IMYA_POLKI = ['до 15 кВт', '15-90 кВт', '90-250 кВт', 'свыше 250 кВт']


def chislo(v):
    if v is None:
        return None
    s = str(v).replace(',', '.').replace(' ', '').replace('\xa0', '').strip()
    try:
        return float(s)
    except Exception:
        return None


def da(v):
    return str(v or '').strip().lower().startswith('да')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--export', required=True)
    ap.add_argument('--out', default=os.path.join(DIR, 'karta.json'))
    a = ap.parse_args()

    # site -> список карточек
    tovary = collections.defaultdict(list)
    vidennye = set()
    vsego = 0
    with open(a.export, encoding='utf-8-sig', newline='') as fh:
        for row in csv.DictReader(fh, delimiter=';'):
            kl = (row.get('IE_XML_ID') or row.get('IE_ID')
                  or row.get(KOL['imya']) or '').strip()
            if not kl or kl in vidennye:
                continue
            vidennye.add(kl)
            vsego += 1
            b = (row.get(KOL['brend']) or '').strip().lower()
            site = next((v for k, v in SAYT.items() if k in b), None)
            if not site:
                continue
            tovary[site].append({
                'model': (row.get(KOL['imya']) or '').strip(),
                'kvt': chislo(row.get(KOL['kvt'])),
                'bar': chislo(row.get(KOL['bar'])),
                'lmin': chislo(row.get(KOL['lmin'])),
                'resiver_l': chislo(row.get(KOL['resiver_l'])),
                'osushitel': da(row.get(KOL['osushitel'])),
                'resiver': da(row.get(KOL['resiver'])),
                'chastotnik': da(row.get(KOL['chastotnik'])),
                'seriya': (row.get(KOL['seriya']) or '').strip(),
                'tsena': chislo(row.get(KOL['tsena'])),
                'gruppa': (row.get(KOL['gruppa']) or '').strip(),
                'tip': (row.get(KOL['tip']) or '').strip(),
            })

    itog = {}
    for site, kart in tovary.items():
        vint = [k for k in kart if 'винтов' in (k['tip'] or '').lower()
                and k['kvt'] and k['lmin']]
        d = {'товаров всего': len(kart), 'винтовых с кВт и л/мин': len(vint)}

        # РАСПРЕДЕЛЕНИЕ ПО МОЩНОСТИ - вместо «посчитай из диапазона».
        raspred = []
        for (lo, hi), imya in zip(POLKI, IMYA_POLKI):
            v = [k for k in vint if lo < k['kvt'] <= hi]
            if not v:
                continue
            ceny = [k['tsena'] for k in v if k['tsena']]
            raspred.append({
                'полка': imya, 'позиций': len(v),
                'подача л/мин': [min(k['lmin'] for k in v),
                                 max(k['lmin'] for k in v)],
                'с частотником': sum(1 for k in v if k['chastotnik']),
                'с ресивером': sum(1 for k in v if k['resiver']),
                'с осушителем': sum(1 for k in v if k['osushitel']),
                'позиций с ценой': len(ceny),
                'медиана цены': round(statistics.median(ceny)) if ceny else None,
            })
        d['распределение по мощности'] = raspred

        # ПОДАЧА ПРИ КОНКРЕТНОМ ДАВЛЕНИИ. Владелец: «отбираем реальные
        # модели, которые дают требуемую подачу ИМЕННО ПРИ 10 бар».
        po_davleniyu = {}
        for bar in sorted({k['bar'] for k in vint if k['bar']}):
            v = [k for k in vint if k['bar'] == bar]
            if len(v) < 3:
                continue
            po_davleniyu[f'{bar:g} бар'] = {
                'позиций': len(v),
                'подача л/мин': [min(k['lmin'] for k in v),
                                 max(k['lmin'] for k in v)],
                'мощность кВт': [min(k['kvt'] for k in v),
                                 max(k['kvt'] for k in v)],
            }
        d['по давлению'] = po_davleniyu

        # ОБРАЗЦЫ КАРТОЧЕК для примера подбора: по одной из каждой полки,
        # с полным набором величин ОДНОЙ машины. Именно этого не хватало:
        # из концов диапазона машину не собрать.
        obraztsy = []
        for (lo, hi), imya in zip(POLKI, IMYA_POLKI):
            v = sorted([k for k in vint if lo < k['kvt'] <= hi],
                       key=lambda k: k['lmin'])
            if v:
                k = v[len(v) // 2]
                obraztsy.append({
                    'полка': imya, 'модель': k['model'][:70],
                    'кВт': k['kvt'], 'бар': k['bar'], 'л/мин': k['lmin'],
                    'ресивер л': k['resiver_l'], 'частотник': k['chastotnik'],
                    'осушитель': k['osushitel'], 'цена': k['tsena'],
                })
        d['образцы карточек'] = obraztsy

        # ВСТРОЕННЫЕ РЕСИВЕРЫ покарточно - объясняет разрыв с правилом
        # «10-20% минутной производительности».
        res = [(k['resiver_l'], k['lmin']) for k in vint
               if k['resiver_l'] and k['lmin']]
        if res:
            doli = [r / l * 100 for r, l in res if l]
            d['встроенный ресивер'] = {
                'позиций с ресивером': len(res),
                'объём л': [min(r for r, _ in res), max(r for r, _ in res)],
                'доля от минутной подачи, %': [round(min(doli), 1),
                                               round(max(doli), 1)],
                'медиана доли, %': round(statistics.median(doli), 1),
            }
        itog[site] = d

    with open(a.out, 'w', encoding='utf-8') as fh:
        json.dump(itog, fh, ensure_ascii=False, indent=1)
        fh.flush(); os.fsync(fh.fileno())

    print(f'товаров в выгрузке: {vsego}, сайтов: {len(itog)}\n')
    for site, d in sorted(itog.items()):
        print(f'{site}: винтовых {d["винтовых с кВт и л/мин"]}')
        for r in d['распределение по мощности']:
            print(f'   {r["полка"]:<14} {r["позиций"]:>4} поз, '
                  f'{r["подача л/мин"][0]:g}-{r["подача л/мин"][1]:g} л/мин, '
                  f'частотник {r["с частотником"]}, цена у {r["позиций с ценой"]}')
        vr = d.get('встроенный ресивер')
        if vr:
            print(f'   встроенный ресивер: {vr["объём л"][0]:g}-{vr["объём л"][1]:g} л, '
                  f'медиана {vr["медиана доли, %"]}% от минутной подачи')
    print(f'\n-> {a.out}')


if __name__ == '__main__':
    main()
