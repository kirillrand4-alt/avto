# -*- coding: utf-8 -*-
r"""Выгрузка ЕГРЗ за окно + сверка с нашей базой.

Что делает: берёт заключения экспертизы (collector_egrz), пишет их durable в
egrz_<окно>.jsonl с fsync, затем сверяет каждый ИНН с enrich.db — есть ли
компания у нас, есть ли почта и телефон, какое направление — и раскладывает по
профилю КЦ/Meyer по лексике объекта. На выходе CSV рядом с jsonl.

Почему durable: результат серверного прогона, который живёт только в возвращаемом
JSON, теряется при рестарте песочницы (урок 25.07). Здесь он ложится на диск
сервера, и повторный запуск его не трогает — пишется новый файл по метке окна.
"""
import csv
import io
import json
import os
import re
import sqlite3
import sys
import time

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender\_tmp')
БАЗА = r'C:\sender\enrich.db'

# Лексика направлений. КЦ — там, где нужен сжатый воздух, азот, кислород:
# это почти любое производство, поэтому берём признаки отрасли, а не слово
# «компрессор» (в заключении экспертизы его не будет никогда).
КЦ = [
    'нефт', 'газ', 'скважин', 'промысл', 'цпс', 'сикн', 'упн', 'установк подготовк',
    'химич', 'полимер', 'пластик', 'резин', 'лакокрас', 'удобрен', 'аммиак', 'метанол',
    'металлург', 'прокат', 'литейн', 'сталеплав', 'ферросплав', 'обогатительн', 'руд',
    'машиностро', 'станк', 'судостро', 'вагон', 'автомобил', 'приборостро', 'электрон',
    'цемент', 'известк', 'кирпич', 'бетон', 'жби', 'стекл', 'керамич',
    'деревообраб', 'фанер', 'целлюлоз', 'бумаг', 'картон', 'лесопил',
    'фармацевт', 'медицинск издел', 'стерил',
    'птицефабрик', 'свиновод', 'животновод', 'молочн', 'мясоперераб', 'убойн',
    'пивовар', 'напитк', 'спирт', 'дрожж',
    'энергоцентр', 'котельн', 'тэц', 'газопоршн', 'компрессорн', 'азотн', 'кислородн',
]
MEYER = [
    'зерно', 'элеватор', 'зерносуш', 'зерноочист', 'семен', 'калибров',
    'крупян', 'мукомол', 'комбикорм', 'масличн', 'маслоэкстракц', 'подсолнечник',
    'орех', 'сухофрукт', 'овощ', 'картофел', 'ягод', 'заморозк', 'консервн',
    'кофе', 'чай', 'специй', 'сортиров', 'фасов', 'упаковочн', 'пищев', 'хлебозавод',
    'кондитерск', 'молокозавод', 'рыбоперераб', 'рыбн',
]


def профиль(текст):
    t = (текст or '').lower()
    м = sum(1 for k in MEYER if k in t)
    к = sum(1 for k in КЦ if k in t)
    if м and м >= к:
        return 'meyer'
    if к:
        return 'kc'
    return ''


def main():
    дней = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    import collector_egrz as C

    t0 = time.time()
    items = C.col_egrz(days=дней, max_items=None)
    собрано_сек = round(time.time() - t0, 1)

    метка = time.strftime('%d%m')
    jsonl = os.path.join(DIR, 'egrz_%dd_%s.jsonl' % (дней, метка))
    with io.open(jsonl, 'w', encoding='utf-8') as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())

    инны = sorted({(i.get('inn') or '').strip() for i in items if (i.get('inn') or '').strip()})
    c = sqlite3.connect('file:%s?mode=ro' % БАЗА, uri=True, timeout=60)
    есть, почты, телефоны, направления = set(), {}, {}, {}
    ПОРЦИЯ = 400
    for i in range(0, len(инны), ПОРЦИЯ):
        куск = инны[i:i + ПОРЦИЯ]
        з = ','.join('?' * len(куск))
        for (inn, div) in c.execute(
                "select inn, coalesce(division,'') from companies where inn in (%s)" % з, куск):
            есть.add(str(inn))
            направления[str(inn)] = div
        for (inn, n) in c.execute(
                'select inn, count(*) from emails where inn in (%s) group by 1' % з, куск):
            почты[str(inn)] = n
        for (inn, n) in c.execute(
                'select inn, count(*) from phone_contacts where inn in (%s) group by 1' % з, куск):
            телефоны[str(inn)] = n
    c.close()

    строки = []
    for it in items:
        inn = (it.get('inn') or '').strip()
        текст = ' '.join(str(it.get(k) or '') for k in ('what', 'title', 'functional_purpose'))
        строки.append({
            'ИНН': inn,
            'компания': it.get('company_name') or '',
            'объект': (it.get('what') or it.get('title') or '')[:300],
            'регион': it.get('region') or '',
            'дата_заключения': (it.get('pubDate') or '')[:10],
            'вид_работ': it.get('work_type') or '',
            'профиль': профиль(текст),
            'есть_у_нас': 'да' if inn in есть else 'нет',
            'направление_в_базе': направления.get(inn, ''),
            'почт_в_базе': почты.get(inn, 0),
            'телефонов_в_базе': телефоны.get(inn, 0),
            'ссылка': it.get('link') or '',
        })

    csv_путь = os.path.join(DIR, 'egrz_%dd_%s.csv' % (дней, метка))
    with io.open(csv_путь, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(строки[0].keys()), delimiter=';')
        w.writeheader()
        w.writerows(строки)
        f.flush()
        os.fsync(f.fileno())

    # Копия на дроп, чтобы забрать в песочницу.
    try:
        import shutil
        shutil.copyfile(csv_путь, os.path.join(r'C:\seostat\drop\drop-storage',
                                               os.path.basename(csv_путь)))
        на_дропе = os.path.basename(csv_путь)
    except Exception as e:  # noqa: BLE001
        на_дропе = 'не скопировано: %r' % (e,)

    новых = sum(1 for s in строки if s['есть_у_нас'] == 'нет')
    итог = {
        'окно_дней': дней,
        'заключений': len(items),
        'собрано_сек': собрано_сек,
        'уникальных_ИНН': len(инны),
        'с_ИНН': sum(1 for s in строки if s['ИНН']),
        'уже_есть_у_нас': len(инны) - len({s['ИНН'] for s in строки if s['есть_у_нас'] == 'нет'}),
        'новых_компаний': len({s['ИНН'] for s in строки if s['есть_у_нас'] == 'нет' and s['ИНН']}),
        'строк_по_новым': новых,
        'профиль_kc': sum(1 for s in строки if s['профиль'] == 'kc'),
        'профиль_meyer': sum(1 for s in строки if s['профиль'] == 'meyer'),
        'профиль_не_определён': sum(1 for s in строки if not s['профиль']),
        'из_них_с_почтой_у_нас': sum(1 for s in строки if s['почт_в_базе']),
        'файлы': {'jsonl': os.path.basename(jsonl), 'csv': os.path.basename(csv_путь),
                  'на_дропе': на_дропе},
    }
    print('===ИТОГ===')
    print(json.dumps(итог, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
