# -*- coding: utf-8 -*-
"""Убрать из очереди предприятия, у которых не осталось НИ ОДНОГО видимого факта.

ПОВОД. Владелец показал карточку ООО «ОПХ» (7802118578): блок «Оборудование —
что уже известно» пуст, подпись «Убрано вами: 7», характеристик 0 — и карточка
всё равно стоит в очереди. Продавец семь раз сказал «не то», это и есть его
приговор, но состояние и место в очереди берутся из полей предприятия и по
оставшимся фактам не пересчитываются. Команда владельца: «пустые компании удали».

ЧТО СЧИТАЕМ ПУСТЫМ. Не «мало фактов», а НОЛЬ ВИДИМЫХ: факт не показан, если его
скрыл продавец (hidden_item kind='fact') ИЛИ его отсеяло правило показа
(rejection_reason живого модуля панели). Именно это видит продавец, а число в
колонке n_facts — нет.

УДАЛЕНИЕ = СКРЫТИЕ, А НЕ DELETE. Строка в hidden_item убирает предприятие из
очереди и возвращается одной строкой обратно. Физическое удаление уничтожило бы
и факты, и телефоны, и работу продавца на карточке — при том что «пусто» здесь
означает «нет доказательства», а не «нет данных».

РАЗБИВКА ПЕЧАТАЕТСЯ ДО ПРИМЕНЕНИЯ: сколько пусто потому, что продавец сам всё
убрал, сколько потому, что правило отсеяло, и сколько таких, у которых фактов не
было вовсе. Это разные истории, и владелец должен видеть их порознь.

По умолчанию СУХОЙ ПРОГОН. Запуск: python pustye_kompanii.py [--apply]
"""
import importlib.util
import io
import json
import os
import sqlite3
import sys
import time
import types
from collections import Counter

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПР = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
ПОТОК = r'C:\seostat\drop\pustye_kompanii.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv
ПРИЧИНА = 'пусто: ни одного видимого факта'


def живой_модуль():
    путь = None
    for к, _д, ф in os.walk(r'C:\seostat\app'):
        if 'centro_medium.py' in ф:
            путь = os.path.join(к, 'centro_medium.py')
            break
    sys.modules.setdefault('bcrypt', types.ModuleType('bcrypt'))
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(путь))))
    сп = importlib.util.spec_from_file_location('cm', путь)
    cm = importlib.util.module_from_spec(сп)
    sys.modules['cm'] = cm
    сп.loader.exec_module(cm)
    print('правило показа из', путь)
    return cm


def main():
    cm = живой_модуль()
    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=30)
    пр = sqlite3.connect(ПР, timeout=30)
    поля = [r[1] for r in пр.execute('PRAGMA table_info(hidden_item)')]
    print('поля hidden_item:', поля)
    скрК = {str(r[0]) for r in пр.execute(
        "SELECT COALESCE(inn,'') FROM hidden_item WHERE kind='company'")}
    скрФ = {str(r[0]) for r in пр.execute(
        "SELECT COALESCE(value,'') FROM hidden_item WHERE kind='fact'")}

    имена = {}
    телефонов = Counter()
    for инн, имя, нтел in цб.execute(
            "SELECT inn, COALESCE(predpriyatie,''), COALESCE(n_phones,0) FROM company"):
        имена[str(инн)] = имя
        телефонов[str(инн)] = int(нтел or 0)
    видимые = set(имена) - скрК

    всего_ф = Counter()
    видно_ф = Counter()
    убрал_продавец = Counter()
    отсеяло_правило = Counter()
    for rid, инн, м, т, ср, ц, д, ст in цб.execute(
            "SELECT rowid, inn, COALESCE(model,''), COALESCE(equipment_type,''), "
            "COALESCE(medium,''), COALESCE(quote,''), COALESCE(evidence,''), "
            "COALESCE(status,'') FROM fact"):
        и = str(инн)
        if и not in видимые:
            continue
        всего_ф[и] += 1
        if str(rid) in скрФ:
            убрал_продавец[и] += 1
            continue
        if cm.rejection_reason({'model': м, 'equipment_type': т, 'medium': ср,
                                'quote': ц, 'evidence': д, 'status': ст}):
            отсеяло_правило[и] += 1
            continue
        видно_ф[и] += 1
    цб.close()

    стат = Counter()
    к_скрытию = []
    примеры = {'продавец убрал всё': [], 'правило отсеяло всё': [],
               'фактов не было вовсе': [], 'смешанно': []}
    for и in sorted(видимые):
        if видно_ф.get(и, 0) > 0:
            continue
        всего = всего_ф.get(и, 0)
        уб, от = убрал_продавец.get(и, 0), отсеяло_правило.get(и, 0)
        если = ('фактов не было вовсе' if всего == 0 else
                'продавец убрал всё' if уб and not от else
                'правило отсеяло всё' if от and not уб else 'смешанно')
        стат[если] += 1
        стат['ВСЕГО ПУСТЫХ'] += 1
        if телефонов.get(и, 0):
            стат['   у них есть телефон (всё равно звонить не о чем)'] += 1
        if len(примеры[если]) < 6:
            примеры[если].append(
                f'{и} {имена.get(и, "")[:44]} | фактов {всего}, убрал продавец {уб}, '
                f'отсеяло правило {от}, телефонов {телефонов.get(и, 0)}')
        к_скрытию.append((и, если, всего, уб, от))

    print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))
    for имя, сп in примеры.items():
        if сп:
            print(f'\n=== {имя}')
            for с in сп:
                print('  ', с)

    if not ПРИМЕНИТЬ:
        print('\nСУХОЙ ПРОГОН, ничего не скрыто')
        пр.close()
        return

    # СЧИТАЕМ ИЗМЕНЁННЫЕ СТРОКИ ИЗ БАЗЫ, а не длину списка намерений.
    до = пр.execute("SELECT COUNT(*) FROM hidden_item WHERE kind='company'").fetchone()[0]
    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    for и, если, всего, уб, от in к_скрытию:
        зн = {'kind': 'company', 'inn': и, 'value': и,
              'reason': f'{ПРИЧИНА} ({если}: было {всего}, убрал продавец {уб}, '
                        f'отсеяло правило {от})',
              'created_at': ts, 'updated_at': ts, 'username': 'system'}
        имена_к = [к for к in поля if к in зн]
        try:
            пр.execute(
                f"INSERT OR IGNORE INTO hidden_item ({','.join(имена_к)}) "
                f"VALUES ({','.join('?' * len(имена_к))})",
                [зн[к] for к in имена_к])
        except Exception as ex:  # noqa: BLE001
            print('не вставилось', и, str(ex)[:90])
            break
    пр.commit()
    стало = пр.execute("SELECT COUNT(*) FROM hidden_item WHERE kind='company'").fetchone()[0]
    пр.close()

    with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
        for и, если, всего, уб, от in к_скрытию:
            ф.write(json.dumps({'ts': ts, 'inn': и, 'pochemu': если,
                                'faktov': всего, 'ubral_prodavec': уб,
                                'otseyalo_pravilo': от,
                                'name': имена.get(и, '')}, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())

    print(f'\nскрытий предприятий было {до}, стало {стало}, '
          f'ПРИБАВИЛОСЬ {стало - до}')
    print(f'видимых предприятий было {len(видимые)}, '
          f'стало {len(видимые) - (стало - до)}')
    print('вернуть любое: удалить его строку из hidden_item; '
          f'список сохранён в {ПОТОК}')


if __name__ == '__main__':
    main()
