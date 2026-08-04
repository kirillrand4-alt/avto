# -*- coding: utf-8 -*-
"""Пересмотр 99 скрытий, отобранных запросом, слепым к прописным буквам.

ОТКУДА СПИСОК. 3-я сессия выложила `VAZHNOE-3s-SKRYTIYA-PREDPRIYATIY-k-
peresmotru.csv`: 97 предприятий скрыты с причиной «центробежность не
подтверждена ни одним фактом», ещё 2 — приговором суда моделей. Отбор шёл
запросом `lower(quote) like '%центробежн%'`, а SQL кириллицу не знает. Значит
ноль в том отборе мог означать не «фактов нет», а «фактов не видно».

ЧТО ПРОВЕРЯЮ И ЧЕМ. Не изобретаю новое правило центробежности: беру то, что уже
работает в панели — `centro_medium.rejection_reason`. Оно знает и тепловозный
ТК-23С, и паровой турбоагрегат, и автомобильную турбину, и садовую воздуходувку.
Порядок такой:
  1) все факты предприятия читаю ПИТОНОМ (кириллица, любой регистр);
  2) слово нашей машины ищу в цитате регуляркой с `re.I`;
  3) факт, который общее правило признаёт мусором, в доказательство НЕ идёт.

ЧЕГО НЕ ДЕЛАЮ. Автоматически ничего не возвращаю: скрытие снимает человек,
увидев цитату. Оп готовит список с цитатой и ссылкой — глазами, а не счётчиком.
Правило дня: близость не доказывает принадлежность, а число не доказывает
правоту.

Запуск: python peresmotr_99_skrytiy.py
"""
import csv
import io
import os
import re
import sqlite3
import sys
from collections import Counter

# Где модуль лежит НА САМОМ ДЕЛЕ, выяснено обходом файловой системы, а не
# догадкой: `C:\seostat\app\services\centro_medium.py`. В репозитории он
# живёт в `panel_centro/`, на сервере — в `app/services/`, и два слепых импорта
# подряд промахнулись именно поэтому. Ищем путь, а не сочиняем.
for _п in (r'C:\seostat\app\services', r'C:\seostat\app', r'C:\seostat'):
    sys.path.insert(0, _п)
ДРОП = r'C:\seostat\drop\drop-storage'
ФАЙЛ = 'VAZHNOE-3s-SKRYTIYA-PREDPRIYATIY-k-peresmotru.csv'
ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ВЫХОД = r'C:\seostat\drop\drop-storage\PERESMOTR-99-SKRYTIY-1S.csv'

НАША_МАШИНА = re.compile(
    r'центробежн\w*|турбокомпрессор\w*|турбовоздуходувк\w*|турбогазодувк\w*|'
    r'турбоагрегат\w*\s+возду|нагнетател\w*|\bцк[\s-]?\d|\bк-?\d{3}-\d{2}|'
    r'\b\d{2}вц[\s-]?\d|воздуходувк\w*', re.I)

try:
    import centro_medium as CM
except Exception:  # noqa: BLE001
    try:
        from app.services import centro_medium as CM
    except Exception as ex:  # noqa: BLE001
        print('НЕ ИМПОРТИРУЕТСЯ centro_medium:', str(ex)[:120])
        CM = None


def main():
    путь = os.path.join(ДРОП, ФАЙЛ)
    if not os.path.exists(путь):
        print('НЕТ ФАЙЛА:', путь)
        return
    строки = list(csv.DictReader(
        io.open(путь, encoding='utf-8-sig'), delimiter=';'))
    цели = {re.sub(r'\D', '', str(р.get('inn') or '')): р for р in строки}
    print(f'в списке {len(строки)} строк, различных ИНН {len(цели)}')
    if CM is None:
        print('без общего правила проверку не веду — это был бы новый заслон')
        return

    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True)
    поля = [r[1] for r in цб.execute('PRAGMA table_info(fact)')]
    выбор = [к for к in ('inn', 'quote', 'medium', 'equipment_type', 'source',
                         'source_url', 'title') if к in поля]
    факты = {}
    for р in цб.execute(f"SELECT {','.join(выбор)} FROM fact"):
        д = dict(zip(выбор, р))
        и = re.sub(r'\D', '', str(д.get('inn') or ''))
        if и in цели:
            факты.setdefault(и, []).append(д)
    цб.close()

    стат = Counter()
    к_возврату = []
    for инн, р in цели.items():
        мои = факты.get(инн, [])
        стат['фактов нет вовсе' if not мои else 'факты есть'] += 1
        доказательства = []
        for ф in мои:
            текст = ' '.join(str(ф.get(к) or '') for к in
                             ('quote', 'title', 'equipment_type'))
            if not НАША_МАШИНА.search(текст):
                continue
            причина = CM.rejection_reason(ф)
            if причина:
                стат[f'   отсеяно общим правилом: {причина}'] += 1
                continue
            доказательства.append(ф)
        if доказательства:
            стат['ЕСТЬ ДОКАЗАТЕЛЬСТВО — скрытие под вопросом'] += 1
            ф = доказательства[0]
            к_возврату.append({
                'inn': инн,
                'prichina_skrytiya': str(р.get('prichina') or '')[:80],
                'dokazatelstv': len(доказательства),
                'citata': str(ф.get('quote') or '')[:300],
                'sreda': str(ф.get('medium') or ''),
                'ssylka': str(ф.get('source_url') or ''),
                'istochnik': str(ф.get('source') or '')})
        else:
            стат['доказательств нет — скрытие стоит'] += 1

    for з in к_возврату[:10]:
        print(f"   {з['inn']} [{з['dokazatelstv']}] {з['citata'][:96]}")
    if not к_возврату:
        print('   ни одного — все 99 скрыты по делу')

    if к_возврату:
        with io.open(ВЫХОД, 'w', encoding='utf-8-sig', newline='') as ф:
            п = csv.DictWriter(ф, fieldnames=list(к_возврату[0]), delimiter=';')
            п.writeheader()
            п.writerows(к_возврату)
            ф.flush()
            os.fsync(ф.fileno())
        print('файл:', os.path.basename(ВЫХОД))

    print()
    for к, v in стат.most_common():
        print(f'{к:56} {v:5}')


if __name__ == '__main__':
    main()
