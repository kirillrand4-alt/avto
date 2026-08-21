#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Лестница цены по чистоте азота и кислорода - из нашего же прайса.

    python3 chistota.py --export <bitrix.csv|->  [--out chistota.json]

ЗАЧЕМ. В готовом ТЗ азотной станции ЗИФ блок цены получился правильным
по смыслу и пустым по существу: «станция на 99,999% дороже станции
на 95% в несколько раз». «В несколько раз» - это то самое правдоподобное,
которое мы запрещаем. И запрещаем правильно: в payload страницы чистоты
нет вообще, взять величину было неоткуда.

А она у нас есть. В выгрузке чистота лежит отдельным свойством
(IP_PROP22750), рядом с ценой, и по ним считается ЛЕСТНИЦА МНОЖИТЕЛЕЙ:
во сколько раз дороже позиция на 99,9% против позиции на 95% при прочих
равных. Это не оценка и не рынок - это наш прайс, его можно назвать
в тексте и за него можно ответить.

ПОЧЕМУ МНОЖИТЕЛИ, А НЕ ЦЕНЫ. Абсолютные цены живут в карточках
и обновляются выгрузкой; назвать их в тексте значит через месяц соврать.
Отношение между ступенями чистоты держится куда дольше и остаётся верным
даже после переоценки.

ПОЧЕМУ ПРИ РАВНОЙ ПОДАЧЕ, И ЭТО ГЛАВНОЕ. Первая версия считала медиану
цены по всей ступени и дала лестницу, которая НЕ РАСТЁТ: 99,9% дешевле
99,5%, а 99,999% дешевле 99,99%. Причина ровно та, от которой мы весь
проект защищаемся: на разных ступенях лежат РАЗНЫЕ МАШИНЫ, и сравнение
медиан сравнивает не чистоту, а размер. Чистота дорожает, но в выборке
на 99,9% случайно оказались машины помельче, и это перевесило.

Считать можно только внутри ОДНОЙ ПОДАЧИ: берём значение л/мин, где
в каталоге есть позиции нескольких ступеней чистоты, и меряем отношение
там. Тогда размер зафиксирован и меняется только чистота. Так лестница
выходит монотонной и на каждой ступени подтверждается десятком значений
подачи независимо.

Это тот же урок, что с концами диапазона, только этажом выше: там нельзя
делить максимум на максимум, здесь нельзя сравнивать медиану с медианой.
Обе ошибки дают правдоподобное число из несуществующей машины.

ДЕДУПЛИКАЦИЯ ОБЯЗАТЕЛЬНА, как и везде с этой выгрузкой: Битрикс дублирует
строку товара на каждое множественное значение свойства, 600 738 строк
на 27 477 товаров. Читающий построчно завышает счёт в двадцать раз.

ЧТО ЭТО НЕ ЗНАЧИТ. Даже при равной подаче это разные позиции каталога,
а не одна машина в двух исполнениях. Величина описывает НАШ ПРАЙС
(«при одной и той же производительности позиция на 99,999% у нас
в среднем в 2,6 раза дороже позиции на 98%»), а не прибавку к цене
конкретного заказа. Формулировка в ТЗ обязана говорить именно так,
и разброс называть тоже: он широкий.
"""
import argparse, collections, csv, json, os, re, statistics, sys

csv.field_size_limit(10 ** 7)
DIR = os.path.dirname(os.path.abspath(__file__))

KOL = {'xml': 'IE_XML_ID', 'imya': 'IE_NAME', 'tsena': 'IP_PROP22704',
       'brend': 'IP_PROP22553', 'tip': 'IP_PROP22892',
       'chistota': 'IP_PROP22750', 'lmin': 'IP_PROP22571'}

# Ступень попадает в лестницу, если подтверждена столькими независимыми
# значениями подачи. Три - это уже не совпадение, но и не статистика:
# разброс печатаем рядом, чтобы величину нельзя было выдать за точную.
MIN_NABL = 3

# Нормативный ряд чистоты. Владелец поправил выдуманную лестницу «95%»:
# в прайсе ступени именно такие.
RYAD = [95.0, 98.0, 99.0, 99.5, 99.9, 99.99, 99.999]
GAZ = {'азот': r'азот|nitrogen|\bN2\b', 'кислород': r'кислород|oxygen|\bO2\b'}


def chislo(v):
    if v is None:
        return None
    s = str(v).replace(',', '.').replace(' ', '').replace('\xa0', '').strip()
    try:
        return float(s)
    except Exception:
        return None


def stupen(v):
    """Значение чистоты к ближайшей ступени нормативного ряда."""
    p = chislo(re.sub(r'[^\d.,]', '', str(v or '').replace(',', '.')))
    if p is None or not (50 <= p <= 100):
        return None
    return min(RYAD, key=lambda r: abs(r - p))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--export', required=True, help='CSV или - для stdin')
    ap.add_argument('--out', default=os.path.join(DIR, 'chistota.json'))
    a = ap.parse_args()

    fh = sys.stdin if a.export == '-' else open(a.export, encoding='utf-8-sig',
                                                newline='')
    # газ -> подача л/мин -> ступень -> список цен
    po_gazu = collections.defaultdict(
        lambda: collections.defaultdict(lambda: collections.defaultdict(list)))
    vidennye, vsego, s_chistotoy = set(), 0, 0
    for row in csv.DictReader(fh, delimiter=';'):
        kl = (row.get(KOL['xml']) or row.get(KOL['imya']) or '').strip()
        if not kl or kl in vidennye:
            continue
        vidennye.add(kl)
        vsego += 1
        st = stupen(row.get(KOL['chistota']))
        if st is None:
            continue
        s_chistotoy += 1
        ts = chislo(row.get(KOL['tsena']))
        pod = chislo(row.get(KOL['lmin']))
        if not ts or ts <= 0 or not pod:
            continue
        opis = ' '.join(str(row.get(k) or '') for k in
                        (KOL['imya'], KOL['tip'], KOL['brend']))
        for gaz, rx in GAZ.items():
            if re.search(rx, opis, re.I):
                po_gazu[gaz][pod][st].append(ts)
                break

    itog = {}
    for gaz, po_pod in po_gazu.items():
        # только та подача, где есть с чем сравнивать
        po_pod = {p: d for p, d in po_pod.items() if len(d) >= 2}
        if not po_pod:
            continue
        # (база, ступень) -> отношения, собранные независимо по подачам
        otn = collections.defaultdict(list)
        for pod, po_st in po_pod.items():
            b = min(po_st)
            baza = statistics.median(po_st[b])
            for st in po_st:
                if st != b:
                    otn[(b, st)].append(statistics.median(po_st[st]) / baza)
        if not otn:
            continue
        # ведём лестницу от самой частой базы
        bazy = collections.Counter(b for b, _ in otn)
        baza_st = bazy.most_common(1)[0][0]
        lestnitsa = []
        for (b, st), v in sorted(otn.items()):
            if b != baza_st or len(v) < MIN_NABL:
                continue
            lestnitsa.append({
                'чистота, %': st, 'значений подачи': len(v),
                'множитель к базе': round(statistics.median(v), 2),
                'разброс': [round(min(v), 2), round(max(v), 2)],
            })
        if not lestnitsa:
            continue
        itog[gaz] = {
            'база, % чистоты': baza_st,
            'считано при равной подаче': True,
            'значений подачи в основе': len(po_pod),
            'лестница': sorted(lestnitsa, key=lambda r: r['чистота, %']),
        }

    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(itog, f, ensure_ascii=False, indent=1)
        f.flush(); os.fsync(f.fileno())

    print(f'товаров (после дедупа): {vsego}, с чистотой: {s_chistotoy}')
    for gaz, d in itog.items():
        print(f'\n{gaz}, база {d["база, % чистоты"]:g}% чистоты, '
              f'при равной подаче ({d["значений подачи в основе"]} значений):')
        for r in d['лестница']:
            print(f'   {r["чистота, %"]:>7g}%  x{r["множитель к базе"]:<5} '
                  f'(подач {r["значений подачи"]:>3}, '
                  f'разброс {r["разброс"][0]}-{r["разброс"][1]})')
    if not itog:
        print('\nлестницу не собрать: не нашлось подачи с двумя ступенями')
    print(f'\n-> {a.out}')


if __name__ == '__main__':
    main()
