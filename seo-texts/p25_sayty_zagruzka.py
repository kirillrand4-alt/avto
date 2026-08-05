# -*- coding: utf-8 -*-
"""Общая загрузка доменов с заслоном «один домен у нескольких предприятий».

ПОЧЕМУ ОТДЕЛЬНЫЙ МОДУЛЬ. Функция `sayty()` скопирована в шести моих каналах, и правило
отбора в каждом своё по мелочи. 2-я сессия нашла случай, который делает это опасным:
`sibur.ru` заявлен собственным сайтом ПЯТИ заводов. Мой заслон
`stranica_podtverzhdaet` засчитывает страницу первым же условием «хост совпадает с
сайтом предприятия» — значит контакт с сайта группы подтвердится для КАЖДОГО из пяти, и
подтверждение будет выглядеть строгим, потому что формально оно строгое: хост совпал.

Это тот же класс, что «номер у нескольких людей»: величина, которая должна быть
уникальной, на деле общая, и общность никто не проверял.

ЗАМЕР ПО МОИМ ФАЙЛАМ: доменов 504, отданы двум и более предприятиям 34. Из них с весом
3, то есть с высшим доверием:

    sibur.ru          6 предприятий
    tn.ru             5
    rusagrogroup.ru   3

Мои нынешние закрытия по ТЗ на таких доменах НЕ стоят — проверено, ноль. Заслон ставится
на будущее: следующий прогон по этим предприятиям иначе принесёт подтверждения, которые
нельзя будет отличить от настоящих.

ЧТО ДЕЛАЕТ ЗАСЛОН. Домен, отданный двум и более ИНН, не выдаётся как СОБСТВЕННЫЙ сайт
предприятия. Но и не выбрасывается: у АО «Апатит» весь раздел закупок с людьми стоит на
`phosagro.ru`, другого места у него нет. Поэтому возвращаются два словаря — свои сайты и
сайты групп, — и вызывающий сам решает, что ему годится. Разделять, а не отсеивать.
"""
import collections
import csv
import glob
import os
import re

OPS = r'C:\sender\_ops'
SAYTY_GLOB = os.path.join(OPS, '3s_p25_sayty*.csv')
csv.field_size_limit(10 ** 8)


def domen(u):
    u = str(u or '').strip().lower()
    u = re.sub(r'^https?://', '', u).split('/')[0].split('?')[0]
    return re.sub(r'^www\.', '', u)


def zagruzit(ves_ot=2):
    """Вернуть (svoi, gruppy, pochemu).

    svoi   — ИНН → домен, который можно считать собственным сайтом предприятия;
    gruppy — ИНН → домен группы: искать на нём можно, «своим» звать нельзя;
    pochemu — ИНН → причина, по которой домен отнесён к группе (для выгрузки).

    Порядок проверок ЕСТЬ правило, и здесь он такой: сперва собираем, КОМУ ЕЩЁ отдан
    домен, и только потом решаем про каждого. Если решать по ходу чтения, первый ИНН
    получит домен своим, а пятый — групповым, и результат будет зависеть от порядка
    строк в файле.
    """
    syrye = []
    for p in sorted(glob.glob(SAYTY_GLOB)):
        try:
            for r in csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';'):
                inn, s = (r.get('inn') or '').strip(), domen(r.get('sayt'))
                v = (r.get('ves') or '').strip()
                if not (inn and s):
                    continue
                if v.isdigit() and int(v) < ves_ot:
                    continue
                syrye.append((inn, s, os.path.basename(p)))
        except Exception:  # noqa: BLE001
            continue

    komu = collections.defaultdict(set)
    for inn, s, _f in syrye:
        komu[s].add(inn)

    svoi, gruppy, pochemu = {}, {}, {}
    for inn, s, _f in syrye:
        if len(komu[s]) >= 2:
            gruppy.setdefault(inn, s)
            pochemu[inn] = ('домен отдан %d предприятиям — это сайт группы, а не завода'
                            % len(komu[s]))
        else:
            svoi.setdefault(inn, s)
    return svoi, gruppy, pochemu


def _samoproverka():
    svoi, gruppy, pochemu = zagruzit()
    obshchie = collections.Counter()
    for inn, s in gruppy.items():
        obshchie[s] += 1
    print('своих доменов %d, групповых %d' % (len(svoi), len(gruppy)))
    print('групповые домены и сколько предприятий на них:')
    for s, n in obshchie.most_common(10):
        print('   %-28s %d' % (s, n))
    # Контроль: ни один домен не должен оказаться и своим, и групповым.
    peresechenie = set(svoi.values()) & set(gruppy.values())
    print('доменов, попавших в оба списка: %d (должно быть 0)' % len(peresechenie))


if __name__ == '__main__':
    _samoproverka()
