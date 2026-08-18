# -*- coding: utf-8 -*-
"""Порция сайтов 1-й сессии: вес, годность и ОТДЕЛЬНАЯ метка «сайт группы».

ПОЧЕМУ МОДУЛЬ, А НЕ РУКАМИ. Порции 001 и 002 я собрал разовым кодом в командной строке, и
теперь правило веса не лежит нигде: чтобы ответить «почему у этого домена вес 2», надо
вспоминать. Правило, которое живёт только в памяти, расходится с данными молча — это уже
случалось у меня дважды (шапки CSV) и один раз сегодня у 3-й сессии (мера 13 вместо 9).

ВЕС — ЭТО СИЛА ДОВОДА, А НЕ УВЕРЕННОСТЬ:

    3  годен          ИНН предприятия найден цифрами на странице этого сайта
    2  годен          название совпало целиком, ИНН на сайте не пишут вовсе
    1  сайт группы    название совпало, но сайт зовёт СЕБЯ иначе и имени завода нет в домене
    1  кандидат       ни ИНН, ни названия — домен из поиска, ничем не подтверждён
    0  негоден        сайта нет или он не открылся

САЙТ ГРУППЫ ОТДАЁТСЯ, НО НЕ КАК СОБСТВЕННЫЙ САЙТ. Просьба 1-й сессии — держать в `company.sayt`
только вес 2 и 3. Домен группы туда попасть не должен: `sibur.ru` заявлен как сайт ПЯТИ разных
ИНН, и если он ляжет собственным сайтом пяти заводов, то любой контакт с него потом
«подтвердится» для каждого из них. При этом выбрасывать его нельзя: у АО «Апатит» весь раздел
закупок с людьми стоит на `phosagro.ru`, и другого места у него нет.

ОДНА ПАРА — ОДИН ОТВЕТ, И ЭТО ПОСЛЕДНИЙ. Файл подтверждений дописывается, а не переписывается:
там лежит и старый ответ по паре, и переснятый. Берётся ПОСЛЕДНИЙ — правило менялось дважды
за смену (появилось самоназвание сайта, потом оговорка про аббревиатуру), и ранние строки
получены прибором, которого больше нет.

Использование:
    python3 p25_otdat_sayty.py            # следующий свободный номер порции
"""
import csv
import os
import sys

BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
VHOD = os.path.join(L, 'P25-SAJTY.csv')
COLS = ['inn', 'predpriyatie', 'sayt', 'priznak', 'ves', 'godnost', 'ssylka_dokazatelstva',
        'citata', 'sam_sebya', 'kak_vzyat']

# исход подтверждения → (вес, годность, признак)
PRAVILO = {
    'подтверждён':      (3, 'годен', 'ИНН предприятия найден в тексте страницы сайта'),
    'название совпало': (2, 'годен', 'название предприятия совпало целиком, ИНН на сайте не указан'),
    'сайт группы':      (1, 'сайт группы', 'домен принадлежит группе, а не этому юрлицу'),
    'не подтверждён':   (1, 'кандидат', 'домен из поиска, ни ИНН, ни названия на нём нет'),
    'сайт не открылся': (0, 'негоден', 'сайт не открылся'),
    'кандидата сайта нет': (0, 'негоден', 'поиск не дал ни одного домена'),
}


def chitat(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';')) \
        if os.path.exists(p) else []


def main():
    och = {r['inn']: r for r in chitat(os.path.join(L, 'P25-OCHERED.csv'))}
    posledniy = {}
    for r in chitat(VHOD):
        i, s = (r.get('inn') or '').strip(), (r.get('sayt') or '').strip()
        if i and s:
            posledniy[(i, s)] = r

    rows = []
    for r in posledniy.values():
        ves, godnost, priznak = PRAVILO.get(r.get('itog'), (0, 'негоден', r.get('itog') or ''))
        rows.append({'inn': r['inn'], 'predpriyatie': r.get('predpriyatie', ''),
                     'sayt': r['sayt'], 'priznak': priznak, 'ves': ves, 'godnost': godnost,
                     'ssylka_dokazatelstva': r.get('ssylka', ''),
                     'citata': (r.get('citata') or '')[:200],
                     'sam_sebya': (r.get('sam_sebya') or '')[:120],
                     'kak_vzyat': r.get('chem_podtverzhden', '')})
    # ПОРЯДОК — ПО СУММЕ ПОКУПОК. Единственная сортировка задачи.
    rows.sort(key=lambda x: (int(och.get(x['inn'], {}).get('mesto') or 10 ** 9), -x['ves']))

    n = 1
    while os.path.exists(os.path.join(L, f'P25-SAYTY-2S-{n:03d}.csv')):
        n += 1
    put = os.path.join(L, f'P25-SAYTY-2S-{n:03d}.csv')
    with open(put, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter=';', extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    svod = Counter((x['ves'], x['godnost']) for x in rows)
    print(f'порция {n:03d}: строк {len(rows)}, предприятий {len({x["inn"] for x in rows})}',
          file=sys.stderr)
    for (v, g), k in sorted(svod.items(), reverse=True):
        print(f'  вес {v} — {g}: {k}', file=sys.stderr)
    print(f'  В company.sayt годятся только вес 2 и 3: '
          f'{sum(k for (v, g), k in svod.items() if v >= 2)}', file=sys.stderr)
    print(f'→ {put}', file=sys.stderr)


if __name__ == '__main__':
    main()
