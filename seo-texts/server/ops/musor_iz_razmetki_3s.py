# -*- coding: utf-8 -*-
"""Свернуть мусорные факты по разметке 3-й сессии — с проверкой, что id ещё те.

ЗАЧЕМ. 3-я сессия разметила факты по ТЕКСТУ цитаты и просила принять её правило:
не проверять мусор полем `equipment_type`, потому что 197 мусорных фактов у нас
этим полем помечены «центробежная». Правило принимаю: решение нельзя проверять
тем полем, на основании которого оно принято.

ГЛАВНАЯ ОСТОРОЖНОСТЬ. Её файл ссылается на факты по `id` (rowid), а разметка
сделана ДО моей чистки дублей (я удалил 2 902 факта). Rowid в sqlite при DELETE
не сдвигаются, но полагаться на это вслепую нельзя: если таблицу когда-нибудь
пересобирали, id укажет на ЧУЖОЙ факт, и мы свернём не то. Поэтому каждая
строка сверяется по ЦИТАТЕ: id принимается, только если текст факта в базе
совпадает с текстом в её файле. Несовпавшие не сворачиваем и считаем отдельно.

СВОРАЧИВАЕМ, А НЕ УДАЛЯЕМ. Пишем скрытие в `hidden_item` (kind='fact') — так
продавец видит «Убрано: N» и может вернуть. Удаление факта необратимо и в чужой
разметке недопустимо.

По умолчанию СУХОЙ ПРОГОН. Запуск: python musor_iz_razmetki_3s.py [--apply]
"""
import csv
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПР = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
ФАЙЛ = os.path.join(r'C:\seostat\drop\drop-storage',
                    'VAZHNOE-3s-MUSOR-FAKTOV-razmetka.csv')
ПРИМЕНИТЬ = '--apply' in sys.argv
ДА = ('да', '1', 'true', 'yes')


def норм(т):
    return re.sub(r'\s+', ' ', str(т or '')).strip().lower()[:120]


def main():
    csv.field_size_limit(10 ** 7)
    if not os.path.exists(ФАЙЛ):
        raise SystemExit(f'нет {os.path.basename(ФАЙЛ)} на дропе')
    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    факты = {r[0]: (норм(r[1]), str(r[2]), norm_inn(r[3]))
             for r in цб.execute(
                 "SELECT rowid, COALESCE(quote,''), COALESCE(equipment_type,''), inn "
                 'FROM fact')}
    цб.close()
    пр = sqlite3.connect(f'file:{ПР}?mode=ro', uri=True, timeout=20)
    уже = {str(r[0]) for r in пр.execute(
        "SELECT COALESCE(value,'') FROM hidden_item WHERE kind='fact'")}
    пр.close()

    к_скрытию, стат = [], Counter()
    with open(ФАЙЛ, encoding='utf-8-sig', errors='replace', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            стат['строк в разметке'] += 1
            if str(r.get('svorachivat') or '').strip().lower() not in ДА:
                стат['она не велела сворачивать'] += 1
                continue
            try:
                ид = int(str(r.get('id') or '0').strip())
            except ValueError:
                стат['битый id'] += 1
                continue
            если = факты.get(ид)
            if не_нашлось(если):
                стат['факта с таким id уже нет (моя чистка дублей)'] += 1
                continue
            цит_её = норм(r.get('citata'))
            # СВЕРКА ПО ТЕКСТУ: id без совпадения цитаты не принимаем
            if цит_её and если[0][:80] != цит_её[:80]:
                стат['ID УКАЗЫВАЕТ НА ДРУГОЙ ФАКТ — пропуск'] += 1
                continue
            if str(ид) in уже:
                стат['уже свёрнут'] += 1
                continue
            к_скрытию.append((ид, если[2], str(r.get('musor_vid') or '')[:120]))
            стат['К СВОРАЧИВАНИЮ'] += 1
            стат['  ' + str(r.get('musor_vid') or '')[:46]] += 1

    print(json.dumps({'итог': стат.most_common(14),
                      'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой (--apply)'},
                     ensure_ascii=False, indent=1))
    if not ПРИМЕНИТЬ or not к_скрытию:
        if not ПРИМЕНИТЬ:
            print('сухой прогон. Повторить с --apply')
        return

    пр = sqlite3.connect(ПР, timeout=60)
    пр.execute('PRAGMA busy_timeout=60000')
    было = пр.execute("SELECT COUNT(*) FROM hidden_item WHERE kind='fact'").fetchone()[0]
    сейчас = time.strftime('%Y-%m-%dT%H:%M:%S')
    пр.executemany(
        "INSERT INTO hidden_item (inn, kind, value, reason, username, created_at) "
        "VALUES (?,'fact',?,?,'admin',?)",
        [(инн, str(ид), f'мусор по разметке 3-й сессии: {вид}', сейчас)
         for ид, инн, вид in к_скрытию])
    пр.commit()
    стало = пр.execute("SELECT COUNT(*) FROM hidden_item WHERE kind='fact'").fetchone()[0]
    пр.close()
    print(json.dumps({'скрытий фактов было': было, 'стало': стало,
                      'свёрнуто': стало - было}, ensure_ascii=False))


def не_нашлось(з):
    return з is None


def norm_inn(з):
    return ''.join(ч for ч in str(з or '') if ч.isdigit())


if __name__ == '__main__':
    main()
