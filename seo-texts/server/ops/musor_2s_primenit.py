# -*- coding: utf-8 -*-
"""Применить ЖЁСТКИЕ классы мусорных фактов 2-й сессии к панели.

ПОВОД. Её чистки правили её файл, а факты в панель лью я — значит всё, что она
отсеяла, у продавца осталось. Замер по её `OTZYV-2s-MUSORNYE-FAKTY-VSE.csv`:

    47 246  строк в файле
    30 296    такого факта у меня нет вовсе (её корпус шире)
    16 950    совпало с моими фактами
      8 054      уже скрыто
      5 237      предприятие скрыто
      3 659      ВИДНО ПРОДАВЦУ (это 7 764 факта: один текст лежит дублями)

БЕРЁМ ТОЛЬКО ЖЁСТКИЕ КЛАССЫ — «чужая машина нашим словом» и «марка это позиция
по схеме». Она сверила их выборки руками (15 из 2 376 и построчно 205), и из
текста там прямо следует другая машина.

МЯГКИЙ КЛАСС «в тексте нет ни одного слова машины» ЗДЕСЬ НЕ ТРОГАЕМ — это её же
оговорка и она верная: у заключений ЭПБ объектом бывает узел («фундамент
нагнетателя», «бачок торцевого уплотнения»), а машина названа в соседнем
документе. Такое лечится правилом показа, а не скрытием строк.

Скрытие обратимо (строка в hidden_item), причина пишется словами, список
дублируется в поток с fsync.

По умолчанию СУХОЙ ПРОГОН. Запуск: python musor_2s_primenit.py [--apply]
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
ФАЙЛ = r'C:\seostat\drop\drop-storage\OTZYV-2s-MUSORNYE-FAKTY-VSE.csv'
ПОТОК = r'C:\seostat\drop\musor_2s_primeneno.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv
ЖЁСТКИЕ = ('чужая машина', 'позиция')


def ключ(инн, текст):
    return (str(инн), re.sub(r'\W+', '', str(текст or '').casefold())[:110])


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

    мои = {}
    цитата = {}
    for rid, инн, ц, ст, м in цб.execute(
            "SELECT rowid, inn, COALESCE(quote,''), COALESCE(status,''), "
            "COALESCE(model,'') FROM fact"):
        мои.setdefault(ключ(инн, ц or ст or м), []).append(str(rid))
        цитата[str(rid)] = (ц or ст or м)[:120]
    цб.close()

    стат = Counter()
    к_скрытию = []
    примеры = []
    with io.open(ФАЙЛ, encoding='utf-8-sig', errors='replace', newline='') as ф:
        for р in csv.DictReader(ф, delimiter=';'):
            кл = str(р.get('klass') or '').strip()
            if not any(ж in кл.casefold() for ж in ЖЁСТКИЕ):
                стат['мягкий класс — не трогаю'] += 1
                continue
            инн = str(р.get('inn') or '').strip()
            стат['жёстких строк в файле'] += 1
            if инн not in видимые:
                стат['  предприятие скрыто'] += 1
                continue
            for rid in мои.get(ключ(инн, р.get('tekst')), []):
                if rid in скрФ:
                    стат['  факт уже скрыт'] += 1
                    continue
                стат['  К СКРЫТИЮ'] += 1
                к_скрытию.append((rid, инн, кл, str(р.get('pochemu') or '')[:90]))
                if len(примеры) < 10:
                    примеры.append(f'id={rid} {инн} [{кл}] {цитата.get(rid, "")[:80]}')

    print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))
    print('\nчто уйдёт с карточек:')
    for с in примеры:
        print('  ', с)

    if not ПРИМЕНИТЬ:
        print('\nСУХОЙ ПРОГОН, ничего не скрыто')
        пр.close()
        return

    до = пр.execute("SELECT COUNT(*) FROM hidden_item WHERE kind='fact'").fetchone()[0]
    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    for rid, инн, кл, почему in к_скрытию:
        зн = {'kind': 'fact', 'inn': инн, 'value': rid,
              'reason': f'мусор по разбору 2-й сессии: {кл} — {почему}',
              'created_at': ts, 'updated_at': ts, 'username': 'system'}
        имена_к = [к for к in поля if к in зн]
        try:
            пр.execute(
                f"INSERT OR IGNORE INTO hidden_item ({','.join(имена_к)}) "
                f"VALUES ({','.join('?' * len(имена_к))})",
                [зн[к] for к in имена_к])
        except Exception as ex:  # noqa: BLE001
            print('не вставилось', rid, str(ex)[:90])
            break
    пр.commit()
    стало = пр.execute("SELECT COUNT(*) FROM hidden_item WHERE kind='fact'").fetchone()[0]
    пр.close()

    with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
        for rid, инн, кл, почему in к_скрытию:
            ф.write(json.dumps({'ts': ts, 'fact_id': rid, 'inn': инн,
                                'klass': кл, 'pochemu': почему},
                               ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())
    print(f'\nскрытий фактов было {до}, стало {стало}, ПРИБАВИЛОСЬ {стало - до}')


if __name__ == '__main__':
    main()
