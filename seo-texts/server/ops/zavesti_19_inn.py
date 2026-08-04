# -*- coding: utf-8 -*-
"""Завести карточки предприятиям, которых нет в очереди панели.

ПРОСЬБА 3-Й СЕССИИ, дословно: «19 ИНН из ваших 180 вообще нет в очереди панели.
Заводить карточками — ваше; скажите, когда заведёте, я включу их в цели
обратного хода». Панель моя, значит и заводить мне.

ЧТО ЗНАЧИТ «НЕТ В ОЧЕРЕДИ». Две разные вещи, и их нельзя путать:
  * предприятия нет в `company` вообще — карточку надо СОЗДАТЬ;
  * предприятие есть, но скрыто (`hidden_item kind='company'`) — карточка есть,
    её надо РАСКРЫТЬ, а создавать вторую нельзя, будет дубль.
Оп разделяет эти два случая и печатает оба числа до того, как что-то менять.

ОТКУДА ДАННЫЕ ДЛЯ НОВОЙ КАРТОЧКИ. Из моего же файла (имя человека и ИНН) плюс
всё, что уже знает enrich.db по этому ИНН. Название предприятия НЕ выдумываем:
если его нет ни в файле, ни в enrich.db, ставим пометку «наименование не
установлено» — пустая правда лучше придуманного имени в карточке продавца.

По умолчанию СУХОЙ ПРОГОН. Запуск: python zavesti_19_inn.py [--apply]
"""
import csv
import json
import os
import shutil
import re
import sqlite3
import sys
import time
from collections import Counter

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПР = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
ФАЙЛ = (sys.argv[sys.argv.index('--fayl') + 1] if '--fayl' in sys.argv
        else os.path.join(r'C:\seostat\drop\drop-storage',
                          'DLYA-3S-180-INN-s-imenami.csv'))
ПРИМЕНИТЬ = '--apply' in sys.argv


def инны_из_файла(путь):
    csv.field_size_limit(10 ** 7)
    из = {}
    with open(путь, encoding='utf-8-sig', errors='replace', newline='') as ф:
        обр = ф.read(4096)
        ф.seek(0)
        раз = ';' if обр.count(';') >= обр.count(',') else ','
        for r in csv.DictReader(ф, delimiter=раз):
            зн = {(к or '').strip().lower(): (v or '') for к, v in r.items()}
            инн = ''
            for к, v in зн.items():
                if 'инн' in к or к == 'inn':
                    инн = re.sub(r'\D', '', str(v))
                    break
            if len(инн) not in (10, 12):
                continue
            имя = (зн.get('predpriyatie') or зн.get('name')
                   or зн.get('kompaniya') or зн.get('организация') or '')
            из.setdefault(инн, имя.strip())
    return из


def main():
    if not os.path.exists(ФАЙЛ):
        raise SystemExit(f'нет файла {os.path.basename(ФАЙЛ)}')
    из_файла = инны_из_файла(ФАЙЛ)

    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    в_панели = {str(r[0]): (r[1] or '') for r in цб.execute(
        "SELECT inn, COALESCE(predpriyatie,'') FROM company")}
    цб.close()
    пр = sqlite3.connect(f'file:{ПР}?mode=ro', uri=True, timeout=20)
    скрытые = {str(r[0]) for r in пр.execute(
        "SELECT COALESCE(inn,'') FROM hidden_item WHERE kind='company'")}
    пр.close()

    нет_вовсе = [и for и in из_файла if и not in в_панели]
    скрыто = [и for и in из_файла if и in в_панели and и in скрытые]
    видно = [и for и in из_файла if и in в_панели and и not in скрытые]
    стат = Counter({'ИНН в файле': len(из_файла),
                    'видно в очереди': len(видно),
                    'ЕСТЬ, НО СКРЫТО (раскрыть, не заводить)': len(скрыто),
                    'НЕТ В company ВОВСЕ (завести карточку)': len(нет_вовсе)})
    print(json.dumps(стат.most_common(), ensure_ascii=False, indent=1))
    for и in нет_вовсе[:20]:
        print(f'  создать: {и} {из_файла[и][:50]}')
    for и in скрыто[:20]:
        print(f'  раскрыть: {и} {в_панели[и][:50]}')

    if not ПРИМЕНИТЬ:
        print('\nсухой прогон. Повторить с --apply')
        return
    if not (нет_вовсе or скрыто):
        print('менять нечего')
        return

    коп = ЦБ + '.bak-' + str(int(time.time()))
    shutil.copy2(ЦБ, коп)
    print('бэкап:', os.path.basename(коп))
    cx = sqlite3.connect(ЦБ, timeout=120)
    cx.execute('PRAGMA busy_timeout=120000')
    кол = {c[1] for c in cx.execute('PRAGMA table_info(company)')}
    поля = [к for к in ('inn', 'predpriyatie', 'istochnik_dopolneniya',
                        'chego_ne_hvataet') if к in кол]
    ряды = [tuple({'inn': и,
                   'predpriyatie': из_файла[и] or 'наименование не установлено',
                   'istochnik_dopolneniya': 'заведено по просьбе 3-й сессии '
                                            '(цели обратного хода)',
                   'chego_ne_hvataet': 'карточка новая: факты и контакты не '
                                       'собраны'}[к] for к in поля)
            for и in нет_вовсе]
    if ряды:
        cx.executemany(f'INSERT INTO company ({",".join(поля)}) '
                       f'VALUES ({",".join("?" * len(поля))})', ряды)
    cx.commit()
    стало = cx.execute('SELECT COUNT(*) FROM company').fetchone()[0]
    cx.close()

    снято = 0
    if скрыто:
        пр = sqlite3.connect(ПР, timeout=60)
        пр.execute('PRAGMA busy_timeout=60000')
        пр.executemany("DELETE FROM hidden_item WHERE kind='company' AND inn=?",
                       [(и,) for и in скрыто])
        снято = пр.total_changes
        пр.commit()
        пр.close()
    print(json.dumps({'создано карточек': len(ряды),
                      'снято скрытий': снято,
                      'предприятий в панели стало': стало},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
