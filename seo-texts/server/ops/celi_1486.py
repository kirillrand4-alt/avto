# -*- coding: utf-8 -*-
"""Файл целей на все 1486 предприятий без техЛПР — для dadata и поиска сайтов.

Имя для запроса берём в таком порядке: `companies.name` (полное, из ЕГРЮЛ) →
имя из CSV. Второе ОБРЕЗАНО до 60 символов сборщиком базы, и обрезанное имя
портит запрос в выдачу ровно так же, как обрезанная должность портила роль:
«ГОСУДАРСТВЕННОЕ УНИТАРНОЕ СЕЛЬСКОХОЗЯЙСТВЕННОЕ ПРЕДПРИЯТИЕ М» — по такому
не найдётся ничего. Поэтому обрезанные помечаем `imya_obrezano`, чтобы
потребитель мог сперва добрать полное имя через ЕГРЮЛ.

Порядок — по приоритету из базы (там уже учтены выручка и повод), затем по
наличию марок: где марка названа, разговор предметнее.

Запуск: python celi_1486.py [--out ФАЙЛ] [--src CSV]
"""
import csv
import io
import json
import os
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ДРОП = r'C:\seostat\drop\drop-storage'


def арг(имя, поум):
    return sys.argv[sys.argv.index(имя) + 1] if имя in sys.argv else поум


def main():
    csv.field_size_limit(10 ** 7)
    ист = арг('--src', os.path.join(ДРОП, 'BEZ-TEHLPR-1486.csv'))
    вых = арг('--out', r'C:\seostat\drop\celi-1486.jsonl')
    ряды = list(csv.DictReader(io.StringIO(
        open(ист, encoding='utf-8-sig', errors='replace').read()),
        delimiter=';'))

    cx = EDB.EnrichDB().cx
    из_базы = {}
    for и, н, р, с, в in cx.execute(
            "SELECT inn,COALESCE(name,''),COALESCE(region,''),"
            "COALESCE(site,''),COALESCE(revenue_rub,0) FROM companies"):
        из_базы[и] = (н, р, с, в)

    строки = []
    обрезано = полных = 0
    видели = set()
    for r in ряды:
        и = (r.get('inn') or '').strip()
        if not и:
            continue
        # ДЕДУП ПО ИНН. Источник бывает построчным по ЛЮДЯМ (в базе
        # центробежников 1803 строки на 701 предприятие), и без дедупа
        # потребитель делает по одному запросу на КАЖДУЮ строку: пропуск
        # уже опрошенных считается один раз на старте и внутри файла не
        # спасает. Так ушло около 460 лишних платных запросов к ЕГРЮЛ.
        if и in видели:
            continue
        видели.add(и)
        н_csv = (r.get('predpriyatie') or '').strip()
        н_бд, р_бд, с_бд, в_бд = из_базы.get(и, ('', '', '', 0))
        имя = н_бд or н_csv
        # 60 символов ровно — след обрезки сборщиком; настоящих имён такой
        # длины почти не бывает, а ошибиться в сторону «добрать полное имя»
        # дешевле, чем послать в выдачу обрубок
        обр = (not н_бд) and len(н_csv) >= 60
        обрезано += 1 if обр else 0
        полных += 1 if н_бд else 0
        рег = р_бд or (r.get('region') or '').strip()
        сайт = с_бд or (r.get('sayt') or '').strip()
        try:
            прио = int((r.get('prioritet') or '0').strip() or 0)
        except ValueError:
            прио = 0
        строки.append({
            'inn': и, 'poln': имя, 'krat': имя[:60],
            'region': рег, 'city': рег,
            'site': сайт, 'rev': в_бд, 'revenue_rub': в_бд,
            'okved': '',
            'imya_obrezano': обр,
            'marki': (r.get('marki') or '')[:120],
            'sostoyanie': (r.get('sostoyanie') or ''),
            'prioritet': прио,
        })
    строки.sort(key=lambda s: (-s['prioritet'], -(s['rev'] or 0)))

    with open(вых, 'w', encoding='utf-8') as ф:
        for с in строки:
            ф.write(json.dumps(с, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())

    # числа — перечитыванием файла, не по счётчикам цикла
    n = с_сайтом = с_обрез = 0
    with open(вых, encoding='utf-8') as ф:
        for ln in ф:
            d = json.loads(ln)
            n += 1
            с_сайтом += 1 if d['site'] else 0
            с_обрез += 1 if d['imya_obrezano'] else 0
    print(json.dumps({
        'файл': вых, 'целей': n,
        'имя_полное_из_ЕГРЮЛ': полных,
        'имя_обрезано_нужен_ЕГРЮЛ': с_обрез,
        'уже_с_сайтом': с_сайтом,
        'без_сайта': n - с_сайтом,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
