# -*- coding: utf-8 -*-
"""P25: сайты предприятий от 2-й сессии в карточку продавца.

ЗАЧЕМ. Сайт — не украшение карточки, а ВХОД следующего канала: по нему идёт
обход страниц «Контакты» и «Руководство», а это единственный канал, который
даёт ДОЛЖНОСТЬ рядом с фамилией. Без сайта предприятие в этот канал не попадает
вовсе.

ПОЧЕМУ НЕ ПРОСТО UPDATE. У 2-й сессии в файле есть колонка веса: насколько
уверенно домен принадлежит именно этому ИНН. Домен, найденный по названию в
выдаче, — это ровно та ошибка, которую мы ловили трижды за сутки: близость не
доказывает принадлежность. Поэтому:
  * вес 3 и 2 — пишу;
  * вес 1 и ниже — НЕ пишу, но и не выбрасываю: кладу в `sayt_kandidat`,
    если такая колонка есть, иначе только считаю;
  * занятую клетку `sayt` не перезаписываю никогда: там может стоять домен,
    добытый с первоисточника.

Файлов может быть несколько (001, 002, …) — принимаю списком, каждый со своим
следом в потоке.

Запуск: python p25_vlit_sayty.py <файл1.csv> [файл2.csv ...] [--apply]
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

P25 = r'C:\seostat\data\p25.db'
ОБМЕН = r'C:\seostat\drop\drop-storage'
ПОТОК = r'C:\seostat\drop\p25_vlito_saytov.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv
ФАЙЛЫ = [а for а in sys.argv[1:] if а.lower().endswith('.csv')]
ПОРОГ_ВЕСА = 2


def домен(з):
    д = str(з or '').strip().lower()
    д = re.sub(r'^https?://', '', д)
    д = re.sub(r'^www\.', '', д)
    д = д.split('/')[0].split('?')[0].strip()
    return д if re.match(r'^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$', д) else ''


def вес(р):
    for к in ('ves', 'вес', 'weight', 'uverennost', 'score'):
        if к in р and str(р[к]).strip():
            try:
                return int(float(str(р[к]).replace(',', '.')))
            except ValueError:
                pass
    return 0


def main():
    if not ФАЙЛЫ:
        print('нужно: p25_vlit_sayty.py <файл.csv> [ещё.csv] [--apply]')
        return
    цб = sqlite3.connect(P25, timeout=30)
    поля = {r[1] for r in цб.execute('PRAGMA table_info(company)')}
    if 'sayt' not in поля:
        print('в company нет колонки sayt — не лью, пока не пойму куда')
        цб.close()
        return
    есть_кандидат = 'sayt_kandidat' in поля
    наши = {}
    for и, с in цб.execute("SELECT inn, COALESCE(sayt,'') FROM company"):
        наши[str(и)] = str(с).strip()

    стат = Counter()
    к_записи = []
    for имя in ФАЙЛЫ:
        путь = os.path.join(ОБМЕН, имя)
        if not os.path.exists(путь):
            print('НЕТ ФАЙЛА:', путь)
            стат['файлов не найдено'] += 1
            continue
        сыр = io.open(путь, encoding='utf-8-sig', errors='replace').read()
        первая = сыр.splitlines()[0] if сыр.strip() else ''
        раздел = ';' if первая.count(';') >= первая.count(',') else ','
        строки = list(csv.DictReader(io.StringIO(сыр), delimiter=раздел))
        print(f'{имя}: разделитель {раздел!r}, строк {len(строки)}')
        for р in строки:
            стат['строк всего'] += 1
            инн = re.sub(r'\D', '', str(р.get('inn') or ''))
            д = ''
            for к in ('sayt', 'domen', 'site', 'domain', 'url'):
                д = домен(р.get(к))
                if д:
                    break
            в = вес(р)
            if инн not in наши:
                стат['ОТКЛОНЕНО: ИНН не из наших 491'] += 1
                continue
            if not д:
                стат['ОТКЛОНЕНО: домен не разобран'] += 1
                continue
            if наши[инн]:
                стат['клетка занята — не трогаю'] += 1
                continue
            if в < ПОРОГ_ВЕСА:
                стат[f'вес {в}: в кандидаты, не в карточку'] += 1
                к_записи.append({'inn': инн, 'domen': д, 'ves': в,
                                 'kuda': 'kandidat', 'file': имя})
                continue
            стат[f'вес {в}: В КАРТОЧКУ'] += 1
            к_записи.append({'inn': инн, 'domen': д, 'ves': в,
                             'kuda': 'sayt', 'file': имя})

    for з in к_записи[:10]:
        print(f"   {з['inn']} вес {з['ves']} → {з['kuda']:9} {з['domen'][:40]}")

    if not ПРИМЕНИТЬ:
        print()
        print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))
        print('СУХОЙ ПРОГОН, ничего не записано')
        цб.close()
        return

    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    # Считаем ИЗМЕНЁННЫЕ СТРОКИ, а не выполненные запросы: один ИНН приходит в
    # обоих файлах, и второй UPDATE ничего не меняет (клетка уже занята). Счётчик
    # попыток напечатал бы 98 там, где предприятий 53, — число, которое врёт в
    # свою пользу.
    до_изменений = цб.total_changes
    for з in к_записи:
        if з['kuda'] == 'sayt':
            цб.execute("UPDATE company SET sayt=? WHERE inn=? AND COALESCE(sayt,'')=''",
                       (з['domen'], з['inn']))
        elif есть_кандидат:
            цб.execute("UPDATE company SET sayt_kandidat=? WHERE inn=? "
                       "AND COALESCE(sayt_kandidat,'')=''", (з['domen'], з['inn']))
    цб.commit()
    в_карточку = цб.total_changes - до_изменений
    с_сайтом = цб.execute(
        "SELECT COUNT(*) FROM company WHERE COALESCE(sayt,'')<>''").fetchone()[0]
    цб.close()

    with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
        for з in к_записи:
            ф.write(json.dumps({**з, 'ts': ts}, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())

    print()
    print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))
    print(f'строк карточек изменено: {в_карточку}')
    print(f'ПРЕДПРИЯТИЙ С САЙТОМ: {с_сайтом} из 491')


if __name__ == '__main__':
    main()
