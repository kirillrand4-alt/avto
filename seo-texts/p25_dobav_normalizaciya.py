# -*- coding: utf-8 -*-
"""Пересчёт признака «прямой стол» ТРЕТИЙ раз. Считать номера ЦИФРАМИ, а не строками.

ИСТОРИЯ ОДНОЙ ОШИБКИ, У КОТОРОЙ ОКАЗАЛОСЬ ДВА СЛОЯ.

Слой первый я нашла сама и починила: базы номеров собирались ТОЛЬКО из контактов
с добавочным, поэтому номер, которым пользуется десяток людей без добавочного, для
счётчика выглядел уникальным. Починила первым проходом по всем телефонам, выложила
`P25-DOBAVOCHNYE-3S-002.csv`, ярлык «прямой стол» упал с 18 до 16 и я сочла дело
закрытым.

Слой второй нашла 1-я сессия — по следствию, не по коду: «ярлык спорит с данными,
4 строки». И это верно ДАЖЕ В ПОЧИНЕННОМ ФАЙЛЕ, потому что ключом базы у меня всё
ещё стояла СТРОКА НОМЕРА КАК НАПИСАНА НА СТРАНИЦЕ:

    +7 (343) 2290075     Иванец      -> ключ №1, «людей на базе 4»
    8 (343) 229-00-75    Шония       -> ключ №2, «людей на базе 1»  <- ПРЯМОЙ СТОЛ
    +7 343 229-00-75     Шарифуллина -> ключ №3, «людей на базе 4»

Один номер, три написания, три ключа. Из-за этого прямым столом снова оказался
`8 (495) 664-88-40 доб. 2794` — та самая линия ЭТП ГПБ, про которую я в письме
соседям написала «поймала себя на ней». То есть я второй раз подряд исправила
ТЕКСТ ПИСЬМА, а выгрузка осталась с прежним ярлыком.

Это третий случай одной и той же ошибки за смену: `sqlite3.lower()` не знает
кириллицы и честно молчал; телефоны сравнивались как написаны; теперь снова они же.
Правило пишу отдельной строкой, потому что дважды его выучить не вышло:

    СРАВНИВАТЬ И СЧИТАТЬ — ТОЛЬКО ПО НОРМАЛИЗОВАННОМУ ЗНАЧЕНИЮ.
    Написание есть свойство страницы, а не свойство номера.

ЧТО ЕЩЁ ВСКРЫЛОСЬ ПОПУТНО. Шесть строк выгрузки — точные дубли (тот же ИНН, тот же
человек, тот же номер, тот же добавочный, найденные разными запросами). Дубль
раздувает и число строк, и счётчик людей на базе. Считаю по паре «человек + номер»,
дубли схлопываю, но в поле `nashli_raz` пишу, сколькими запросами найдено: это
провенанс, он накапливается, а не заменяется.

ГРАНИЦА СЧЁТА. Людей на базе считаю по ВСЕМУ потоку, а не по выложенному файлу.
Номер, который делят с человеком, не прошедшим приёмку, всё равно делят — приёмка
это свойство доказательства, а не свойство номера.
"""
import base64
import collections
import csv
import io
import json
import os
import re
import sys

# ФОРМА ЗАПИСЕЙ СНЯТА ПРИБОРОМ (`p25_forma_potokov.py`), А НЕ ВСПОМНЕНА. Первый заход
# сюда читал у всех потоков поле `naydeno` и вернул 5 контактов вместо десятков: у
# обратного хода список зовётся `kontakty`, а значение номера лежит в `znachenie`, а не
# в `nomer`. Поэтому список ниже — пары «поток → как в нём называется список и номер».
POTOKI = (
    # путь                                     список      номер           человек
    (r'C:\sender\_ops\p25-obratnyy.jsonl',     'kontakty', 'znachenie',    'fio'),
    (r'C:\sender\_ops\p25-obratnyy-teh.jsonl', 'kontakty', 'znachenie',    'fio'),
    (r'C:\sender\_ops\p25-dobavochnyy.jsonl',  'naydeno',  'nomer',        'chelovek'),
    (r'C:\sender\_ops\p25-dobit.jsonl',        'naydeno',  'telefon',      'fio'),
    (r'C:\sender\_ops\p25-nomer.jsonl',        'naydeno',  'nomer',        'fio'),
    (r'C:\sender\_ops\p25-dolzhnost.jsonl',    'naydeno',  'telefony',     'chelovek'),
)
VYHOD = r'C:\sender\_ops\P25-DOBAVOCHNYE-3S-003.csv'

DOB = re.compile(r'(?:доб(?:ав(?:очный)?)?\.?|вн(?:утр(?:енний)?)?\.?|ext\.?|#)\s*[:№]?\s*'
                 r'(\d{2,5})\b', re.I)
PLOSHCHADKA_V_TEKSTE = re.compile(
    r'\bЭТП\b|электронн\w+\s+торгов\w+\s+площадк|росэлторг|сбербанк-аст|ргс\s*тендер|'
    r'газпромбанк|gpb|zakupki\.gov|техническ\w+\s+поддержк|служб\w+\s+поддержк', re.I)


def cifry(n):
    """Номер как ЧИСЛО, а не как написан. Единственный допустимый ключ сравнения."""
    c = re.sub(r'\D', '', str(n or ''))
    if len(c) == 11 and c[0] in '78':
        c = '7' + c[1:]
    return c


def chelovek_klyuch(fio):
    """Человек как ключ: без двойных пробелов и регистра. «Шарифуллина  Алена» = одна."""
    return re.sub(r'\s+', ' ', str(fio or '').strip()).lower()


def dobavochnyy_pri_nomere(nomer, citata):
    """Добавочный, стоящий ПОСЛЕ ЭТОГО номера, а не где угодно в цитате.

    Первый заход искал `доб` по всей цитате — и приклеил добавочный 2663 сразу к двум
    номерам Вовка, городскому и МОБИЛЬНОМУ +7 925 785-08-87. Добавочный принадлежал
    городскому; мобильный просто стоял в том же снимке. Это ровно та ошибка, за которую
    я уже заплатила в обратном ходе: БЛИЗОСТЬ НЕ ДОКАЗЫВАЕТ ПРИНАДЛЕЖНОСТЬ, а «где-то в
    том же тексте» не доказывает даже близости.

    Поэтому: найти номер в цитате (сравнивая цифры, а не написание) и смотреть только
    сорок знаков ПОСЛЕ него. Не нашли номер в цитате — добавочного нет, и это честнее
    выдуманного.
    """
    c = cifry(nomer)
    if len(c) != 11 or not citata:
        return ''
    # Номер на странице пишут с любыми разделителями, поэтому ищем по цифрам с
    # необязательным мусором между ними, а не строкой.
    shablon = r'[\+8]?\s*7?' + r'\D{0,3}'.join(c[1:])
    m = re.search(shablon, citata)
    if not m:
        return ''
    md = DOB.search(citata[m.end():m.end() + 40])
    return md.group(1) if md else ''


def zapisi():
    """Все ТЕЛЕФОНЫ из всех потоков, плоским списком. Имена полей — из таблицы POTOKI."""
    for put, spisok, pole_nomera, pole_cheloveka in POTOKI:
        if not os.path.exists(put):
            continue
        for ln in open(put, encoding='utf-8'):
            try:
                z = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if z.get('err'):
                continue
            for n in (z.get(spisok) or []):
                if not isinstance(n, dict):
                    continue
                # У обратного хода в одном списке лежат и телефоны, и почты — вид
                # назван полем `tip`. Почта сюда не идёт: она не бывает линией.
                if (n.get('tip') or 'телефон') != 'телефон':
                    continue
                syroy = n.get(pole_nomera)
                nomera = syroy if isinstance(syroy, list) else [syroy]
                for nom in [x for x in nomera if x]:
                    yield {
                        'inn': z.get('inn', ''),
                        'predpriyatie': z.get('predpriyatie', ''),
                        'sayt': z.get('sayt', ''),
                        'chelovek': (n.get(pole_cheloveka) or z.get(pole_cheloveka)
                                     or z.get('fio') or z.get('chelovek') or ''),
                        'dolzhnost': n.get('dolzhnost') or z.get('dolzhnost') or '',
                        'otkuda_dolzhnost': n.get('otkuda_dolzhnost', ''),
                        'nomer': nom,
                        'dobavochnyy': n.get('dobavochnyy', ''),
                        'ssylka': n.get('ssylka', ''),
                        'pochemu': n.get('pochemu') or n.get('pochemu_stranica', ''),
                        'uverennost': n.get('uverennost', 'высокая'),
                        'citata': n.get('citata', ''),
                        'zapros': n.get('zapros') or z.get('zapros', ''),
                        'otkuda_potok': os.path.basename(put),
                    }


def main():
    vse = list(zapisi())

    # ПЕРВЫЙ ПРОХОД: кто стоит на каждой базе. Ключ — ЦИФРЫ. Люди — нормализованные ФИО.
    na_baze = collections.defaultdict(set)
    predpr_na_baze = collections.defaultdict(set)
    for r in vse:
        b = cifry(r['nomer'])
        if len(b) != 11:
            continue
        if r['chelovek']:
            na_baze[b].add(chelovek_klyuch(r['chelovek']))
        predpr_na_baze[b].add(r['inn'])

    # ВТОРОЙ ПРОХОД: только контакты С ДОБАВОЧНЫМ и с названным человеком.
    # Дубли схлопываем по паре «человек + номер + добавочный», считая находки.
    sobrano = {}
    for r in vse:
        b = cifry(r['nomer'])
        if len(b) != 11 or not r['chelovek']:
            continue
        dob = str(r['dobavochnyy'] or '').strip()
        if not dob:
            dob = dobavochnyy_pri_nomere(r['nomer'], r['citata'])
        if not dob:
            continue
        k = (r['inn'], chelovek_klyuch(r['chelovek']), b, dob)
        if k in sobrano:
            sobrano[k]['nashli_raz'] += 1
            if r['ssylka'] and r['ssylka'] not in sobrano[k]['ssylki']:
                sobrano[k]['ssylki'].append(r['ssylka'])
            continue
        sobrano[k] = dict(r, nashli_raz=1, ssylki=[r['ssylka']] if r['ssylka'] else [])

    sch = collections.Counter()
    stroki = []
    for (inn, _kl, b, dob), r in sorted(sobrano.items()):
        lyudey = len(na_baze[b])
        predpr = len(predpr_na_baze[b])
        if b.startswith('79'):
            # У мобильного добавочного не бывает: это либо чужой добавочный, подхваченный
            # из того же текста, либо мобильный записан рядом с номером приёмной. Не
            # выбрасываю — называю вид. Мобильный сам по себе ценнее любого добавочного.
            vid = 'МОБИЛЬНЫЙ, добавочный при нём сомнителен'
        elif predpr > 1:
            vid = 'ЧУЖАЯ ЛИНИЯ: тот же номер у %d разных предприятий' % predpr
        elif lyudey >= 2:
            vid = 'линия с добавочными: базовый номер у %d человек' % lyudey
        elif PLOSHCHADKA_V_TEKSTE.search(r['citata'] or ''):
            vid = 'линия площадки или поддержки (по тексту страницы)'
        else:
            vid = 'ПРЯМОЙ СТОЛ: базовый номер только у этого человека'
        sch[vid.split(':')[0]] += 1
        if r['uverennost'] and r['uverennost'] != 'высокая':
            sch['  из них привязка не бесспорна'] += 1
        if r['nashli_raz'] > 1:
            sch['  из них найдено более чем одним запросом'] += 1
        stroki.append({
            'inn': inn, 'predpriyatie': r['predpriyatie'], 'chelovek': r['chelovek'],
            'dolzhnost': r['dolzhnost'], 'telefon_kak_napisan': r['nomer'],
            'telefon_ciframi': b, 'dobavochnyy': dob, 'vid': vid,
            'lyudey_na_baze': lyudey, 'predpriyatiy_na_baze': predpr,
            'nashli_raz': r['nashli_raz'],
            'pervoistochnik': 'да' if r['pochemu'] else '',
            'uverennost_privyazki': r['uverennost'],
            'otkuda_dolzhnost': r['otkuda_dolzhnost'],
            'ssylki': ' | '.join(r['ssylki']),
            'chem_podtverzhdena': r['pochemu'], 'otkuda_potok': r['otkuda_potok'],
            'citata': re.sub(r'\s+', ' ', (r['citata'] or ''))[:600],
        })

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(stroki[0].keys()), delimiter=';',
                       extrasaction='ignore')
    w.writeheader()
    w.writerows(stroki)
    open(VYHOD, 'w', encoding='utf-8-sig', newline='').write(buf.getvalue())

    otvet = ''
    url, tok = os.environ.get('DROP_URL', ''), os.environ.get('DROP_TOKEN', '')
    if url and tok:
        import urllib.request
        rq = urllib.request.Request(url.rstrip('/') + '/' + os.path.basename(VYHOD),
                                    data=buf.getvalue().encode('utf-8-sig'), method='PUT')
        rq.add_header('X-Drop-Token', tok)
        try:
            otvet = urllib.request.urlopen(rq, timeout=120).status
        except Exception as e:  # noqa: BLE001
            otvet = 'сбой: %s' % e

    # Счётчики ПОСЛЕДНИМИ: stdout_tail отдаёт хвост вывода.
    print('\n'.join('ПРИМЕР %s | %s | %s доб %s | %s' % (
        s['chelovek'], s['predpriyatie'][:28], s['telefon_kak_napisan'], s['dobavochnyy'],
        s['vid'][:44]) for s in stroki[:12]))
    for k, v in sch.most_common():
        print('REC %s\t%d' % (k, v))
    print('ИТОГ ' + json.dumps({
        'контактов в потоках': len(vse), 'с добавочным и человеком': len(sobrano),
        'по видам': dict(sch), 'файл': os.path.basename(VYHOD), 'дроп': otvet,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
