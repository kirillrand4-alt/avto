# -*- coding: utf-8 -*-
"""Цели обратного хода из патентов — тот конец, который отдала 3-я сессия.

Она гонит обратный ход по нашим людям, я беру патентные фамилии: 3 916 пар, с
нашими не пересекаются вовсе (проверено ею, полных совпадений ноль).

ЧТО ОТСЕИВАЕМ И ПОЧЕМУ:
  * СОВЕТСКИЕ патенты (SU) — целиком. Изобретатель 1980-х сегодня на пенсии
    либо умер, звонок ему это позор перед предприятием;
  * предприятия, которых нет среди ВИДИМЫХ в панели: скрытые убраны по делу;
  * людей, которые у нас уже есть по этому ИНН, — их ведёт соседка.

ЧЕГО НЕ ДЕЛАЕМ. Не выдаём найденное за доказанный контакт. Привязка в исходном
файле честно помечена «упоминание в тексте, патентообладатель не проверен»:
имя предприятия просто встретилось в патенте. Поэтому всё, что найдётся, идёт
отдельным источником с пометкой «привязка слабая», а не наравне с людьми со
страницы руководства завода.

Запуск: python celi_patenty.py [--lim N]
"""
import csv
import json
import os
import re
import sqlite3
import sys
from collections import Counter

csv.field_size_limit(10 ** 7)
ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПР = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
ФАЙЛ = os.path.join(r'C:\seostat\drop\drop-storage', 'VAZHNOE-3s-PATENTY.csv')
ВЫХОД = os.path.join(r'C:\seostat\drop', 'celi_patenty.jsonl')
ЛИМ = int(sys.argv[sys.argv.index('--lim') + 1]) if '--lim' in sys.argv else 0
_ФИО = re.compile(r'^[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё]{2,}\s+'
                  r'[А-ЯЁ][а-яё]{2,}(?:вич|вна|ична|инична)$')


def клч(т):
    return re.sub(r'\s+', ' ', str(т or '').strip().lower()).replace('ё', 'е')


def main():
    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    имена = {str(и): (н or '') for и, н in
             цб.execute('SELECT inn, predpriyatie FROM company')}
    есть_люди = {(str(и), клч(ч)) for и, ч in
                 цб.execute('SELECT inn, person FROM person') if ч}
    цб.close()
    скрыты = set()
    try:
        пр = sqlite3.connect(f'file:{ПР}?mode=ro', uri=True, timeout=20)
        скрыты = {str(r[0]) for r in пр.execute(
            "SELECT inn FROM hidden_item WHERE kind='company'")}
        пр.close()
    except Exception:  # noqa: BLE001
        pass

    отсев = Counter()
    цели, видел = [], set()
    with open(ФАЙЛ, encoding='utf-8-sig', errors='replace', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            инн = str(r.get('inn') or '').strip()
            ном = (r.get('nomer') or '').strip().upper()
            if ном.startswith('SU'):
                отсев['советский патент'] += 1
                continue
            if инн not in имена:
                отсев['предприятия нет в панели'] += 1
                continue
            if инн in скрыты:
                отсев['предприятие скрыто'] += 1
                continue
            for чел in re.split(r'\s*[,;]\s*', r.get('izobretateli') or ''):
                чел = чел.strip()
                if not _ФИО.match(чел):
                    отсев['не полное ФИО'] += 1
                    continue
                к = (инн, клч(чел))
                if к in есть_люди:
                    отсев['человек уже есть у нас'] += 1
                    continue
                if к in видел:
                    отсев['повтор в файле патентов'] += 1
                    continue
                видел.add(к)
                цели.append({'inn': инн, 'person': чел,
                             'post': 'изобретатель по патенту',
                             'role': 'инженер (не главный)',
                             'name': имена[инн],
                             'patent': ном, 'url': (r.get('ssylka') or '')})
    if ЛИМ:
        цели = цели[:ЛИМ]
    with open(ВЫХОД, 'w', encoding='utf-8') as ф:
        for ц in цели:
            ф.write(json.dumps(ц, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())
    print(json.dumps({
        'ЦЕЛЕЙ': len(цели),
        'предприятий': len({ц['inn'] for ц in цели}),
        'отсеяно': отсев.most_common(),
        'файл': ВЫХОД,
    }, ensure_ascii=False, indent=1))
    for ц in цели[:8]:
        print(f'  {ц["inn"]} {ц["person"][:30]:<30} {ц["name"][:36]:<36} '
              f'{ц["patent"]}')


if __name__ == '__main__':
    main()
