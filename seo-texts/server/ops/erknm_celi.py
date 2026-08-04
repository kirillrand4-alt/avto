# -*- coding: utf-8 -*-
"""Список целей для ЕРКНМ — ТОЛЬКО видимые в панели предприятия.

ПОЧЕМУ НЕ 1573. Прямое сужение владельца: «1573 = не надо, надо только те
которые отображаются в базе». Видимое — это то, что осталось после чисток
(не-центробежные, непрофильные) и после ручных скрытий продавца, то есть
именно те карточки, которые продавец реально открывает.

ЧТО СЧИТАЕТСЯ ВИДИМЫМ. Предприятие ИЗ `company`, для которого нет строки
`hidden_item(kind='company')` в `centro_sales.db`. Скрытия по фактам и номерам
на видимость предприятия не влияют — карточка остаётся открытой.

Печатает срез: сколько всего, сколько уже с техническим ЛПР по имени (таким
ЕРКНМ ничего не добавит), сколько без. Пишет CSV в drop-storage, чтобы прогон
ЕРКНМ был резюмируемым и его цели не пересчитывались на каждом запуске.

Запуск: python erknm_celi.py [--csv]
"""
import csv
import json
import os
import sqlite3
import sys
from collections import Counter

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПР = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
ВЫХОД = os.path.join(r'C:\seostat\drop\drop-storage', 'erknm-celi.csv')

РОЛИ_ТЕХ = ('главн', 'энергетик', 'механик', 'технич', 'инженер', 'энерго',
            'ремонт', 'эксплуат', 'кип', 'опо', 'промбез')


def main():
    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    компании = {str(и): (н or '') for и, н in цб.execute(
        "SELECT inn, COALESCE(predpriyatie,'') FROM company")}
    # у кого уже есть технический человек ПО ИМЕНИ — им ЕРКНМ роли не добавит
    с_техчел = set()
    for и, чел, долж, роль in цб.execute(
            "SELECT inn, COALESCE(person,''), COALESCE(position,''), "
            "COALESCE(role,'') FROM person"):
        if not str(чел).strip():
            continue
        т = (str(долж) + ' ' + str(роль)).lower()
        if any(к in т for к in РОЛИ_ТЕХ):
            с_техчел.add(str(и))
    цб.close()

    пр = sqlite3.connect(f'file:{ПР}?mode=ro', uri=True, timeout=20)
    скрытые = {str(r[0]) for r in пр.execute(
        "SELECT COALESCE(inn,'') FROM hidden_item WHERE kind='company'")}
    пр.close()

    видимые = [и for и in компании if и not in скрытые]
    цели = [и for и in видимые if и not in с_техчел]
    стат = Counter({'всего в панели': len(компании),
                    'скрыто продавцом/чистками': len(скрытые),
                    'ВИДИМЫХ': len(видимые),
                    '  из них уже с техчеловеком по имени': len(видимые) - len(цели),
                    '  ЦЕЛИ ЕРКНМ': len(цели)})
    print(json.dumps(стат.most_common(), ensure_ascii=False, indent=1))

    if '--csv' in sys.argv:
        # ЦЕЛИ ДЛЯ ЕРКНМ — ВСЕ ВИДИМЫЕ, а не только «без техчеловека».
        # Причина: имена в архиве достаются даром, когда 338 МБ уже скачаны;
        # отсекать предприятие, у которого одно имя есть, значит терять второе.
        # Ограничение владельца («только то, что отображается в базе») при этом
        # соблюдено полностью — скрытые не берём.
        список = видимые if '--vse-vidimye' in sys.argv else цели
        with open(ВЫХОД, 'w', encoding='utf-8-sig', newline='') as ф:
            w = csv.writer(ф, delimiter=';')
            w.writerow(['inn', 'name', 'tehchelovek_est'])
            for и in список:
                w.writerow([и, компании[и],
                            'да' if и in с_техчел else 'нет'])
        print('записан', ВЫХОД, os.path.getsize(ВЫХОД), 'байт, строк',
              len(список))


if __name__ == '__main__':
    main()
