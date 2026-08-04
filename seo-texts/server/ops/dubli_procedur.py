# -*- coding: utf-8 -*-
"""Склеить дубли одной закупочной процедуры на карточках (файл 2-й сессии).

ПОВОД. Владелец видел на экране процедуру ГП430663 двумя строками: у одной тип
«центробежная», у другой «тип не установлен (марка не опознана)». Это два
обхода 2-й сессии, нашедшие ОДИН документ. Её файл `SROCHNO-1S-DUBLI-PROCEDUR.csv`:
579 групп, до 10 записей на одну процедуру, счётчик «Фактов» завышен.

КЛЮЧ ГРУППЫ — (ИНН + номер процедуры). Номер ищем в моих фактах по цитате,
evidence и ссылке: отдельной колонки под него в fact нет.

КТО ВЫЖИВАЕТ (правило её же, я согласен): запись с НАЗВАННЫМ типом, потом с
маркой, потом со средой; при равенстве — с более длинной цитатой (в ней больше
текста документа). Из пары «центробежная» / «тип не установлен» выживает
первая — карточка перестаёт показывать «марка не опознана» рядом с опознанной.

СКЛЕЙКА = СКРЫТИЕ ПРОИГРАВШИХ, а не DELETE и не слияние полей. Скрытая строка
хранит свой источник и возвращается одной строкой; правка полей выжившего
факта — это уже редактирование доказательства, его не делаем.

По умолчанию СУХОЙ ПРОГОН. Запуск: python dubli_procedur.py [--apply]
"""
import csv
import io
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПР = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
ФАЙЛ = r'C:\seostat\drop\drop-storage\SROCHNO-1S-DUBLI-PROCEDUR.csv'
ПОТОК = r'C:\seostat\drop\dubli_procedur_skleeno.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv

ТИП_НАЗВАН = re.compile(r'центробежн|поршнев|винтов|вихрев|роторн|мембранн', re.I)


def балл(тип, марка, среда, цитата):
    """Чем выше, тем достойнее выжить: тип > марка > среда > длина цитаты."""
    b = 0
    if ТИП_НАЗВАН.search(str(тип)):
        b += 1000
    if str(марка).strip() and 'не опознан' not in str(марка):
        b += 100
    низ = str(среда).casefold()
    if низ.strip() and 'не установлен' not in низ and 'не назван' not in низ:
        b += 10
    return b + min(9, len(str(цитата)) // 200)


def main():
    if not os.path.exists(ФАЙЛ):
        print('НЕТ ФАЙЛА:', ФАЙЛ)
        return
    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=30)
    пр = sqlite3.connect(ПР, timeout=30)
    поля = [r[1] for r in пр.execute('PRAGMA table_info(hidden_item)')]
    скрК = {str(r[0]) for r in пр.execute(
        "SELECT COALESCE(inn,'') FROM hidden_item WHERE kind='company'")}
    скрФ = {str(r[0]) for r in пр.execute(
        "SELECT COALESCE(value,'') FROM hidden_item WHERE kind='fact'")}
    видимые = {str(r[0]) for r in цб.execute('SELECT inn FROM company')} - скрК

    факты = {}
    for rid, инн, м, т, ср, ц, д, у in цб.execute(
            "SELECT rowid, inn, COALESCE(model,''), COALESCE(equipment_type,''), "
            "COALESCE(medium,''), COALESCE(quote,''), COALESCE(evidence,''), "
            "COALESCE(source_url,'') FROM fact"):
        факты.setdefault(str(инн), []).append(
            (str(rid), м, т, ср, ц, (ц + ' ' + д + ' ' + у)))
    цб.close()

    стат = Counter()
    к_скрытию = []
    примеры = []
    with io.open(ФАЙЛ, encoding='utf-8-sig', errors='replace', newline='') as ф:
        for р in csv.DictReader(ф, delimiter=';'):
            инн = str(р.get('inn') or '').strip()
            номер = str(р.get('nomer_procedury') or '').strip()
            стат['групп в файле'] += 1
            if not номер or len(номер) < 6:
                стат['  номер короткий — пропуск'] += 1
                continue
            if инн not in видимые:
                стат['  предприятие скрыто'] += 1
                continue
            наши = [ф_ for ф_ in факты.get(инн, []) if номер in ф_[5]]
            живые = [ф_ for ф_ in наши if ф_[0] not in скрФ]
            if len(живые) < 2:
                стат['  дубля уже нет (0-1 живая запись)'] += 1
                continue
            стат['  ГРУППА С ЖИВЫМ ДУБЛЕМ'] += 1
            живые.sort(key=lambda ф_: -балл(ф_[2], ф_[1], ф_[3], ф_[4]))
            выжил = живые[0]
            for ф_ in живые[1:]:
                к_скрытию.append((ф_[0], инн, номер, выжил[0]))
            if len(примеры) < 8:
                примеры.append(
                    f'{инн} {номер}: выжил id={выжил[0]} [{выжил[2][:24]}], '
                    f'скрыто {len(живые) - 1} (типы: '
                    f'{" | ".join(ф_[2][:20] or "пусто" for ф_ in живые[1:])})')

    print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))
    print(f'к скрытию записей: {len(к_скрытию)}')
    for с in примеры:
        print('  ', с)

    if not ПРИМЕНИТЬ:
        print('\nСУХОЙ ПРОГОН, ничего не скрыто')
        пр.close()
        return

    до = пр.execute("SELECT COUNT(*) FROM hidden_item WHERE kind='fact'").fetchone()[0]
    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    for rid, инн, номер, выжил in к_скрытию:
        зн = {'kind': 'fact', 'inn': инн, 'value': rid,
              'reason': f'дубль процедуры {номер}: тот же документ показан '
                        f'записью id={выжил}',
              'created_at': ts, 'updated_at': ts, 'username': 'system'}
        имена_к = [к for к in поля if к in зн]
        пр.execute(
            f"INSERT OR IGNORE INTO hidden_item ({','.join(имена_к)}) "
            f"VALUES ({','.join('?' * len(имена_к))})",
            [зн[к] for к in имена_к])
    пр.commit()
    стало = пр.execute("SELECT COUNT(*) FROM hidden_item WHERE kind='fact'").fetchone()[0]
    пр.close()

    with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
        for rid, инн, номер, выжил in к_скрытию:
            ф.write(json.dumps({'ts': ts, 'fact_id': rid, 'inn': инн,
                                'nomer': номер, 'vyzhil': выжил},
                               ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())
    print(f'\nскрытий фактов было {до}, стало {стало}, ПРИБАВИЛОСЬ {стало - до}')


if __name__ == '__main__':
    main()
