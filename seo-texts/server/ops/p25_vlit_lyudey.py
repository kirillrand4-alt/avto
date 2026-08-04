# -*- coding: utf-8 -*-
"""P25: приёмка людей из файлов соседних сессий в p25.db с наблюдениями.

ПОЧЕМУ ОТДЕЛЬНЫЙ ОП, А НЕ ПРАВКА ЦЕНТРОБЕЖНОГО. Тот пишет в снимок панели
центробежки и ничего не знает ни про наблюдения, ни про даты подтверждения.
Смешивать две задачи в одном опе — это тот же класс, что признак задачи вместо
отдельной базы: рано или поздно польётся не туда.

ПРИЁМКА (условия ТЗ, я за неё отвечаю):
  * ИНН обязан быть среди наших 491 — иначе строка не наша, откладываю;
  * ССЫЛКА обязательна: без первоисточника строка не принимается вовсе;
  * ДАТА не обязательна, но её отсутствие — отдельный класс: строка принимается
    и в меру «свежих» НЕ идёт, пока дату не нашли. Это дословно правило ТЗ,
    а не моя мягкость;
  * ФИО из двух слов и больше — «Иванов» без имени человеком не считаем.

НАБЛЮДЕНИЕ ПИШЕТСЯ ВСЕГДА, даже когда человек уже есть: три источника — три
строки в `contact_source`, у каждой своя ссылка, дата и цитата. Именно это и
требовал владелец словами «источник в трёх местах — три кликабельные ссылки».

ТРИ ИСХОДА ВСТАВКИ (поправка 3-й сессии, стоила молча потерянных номеров):
завести / дописать номер в ПУСТУЮ клетку / записать вторым номером, старый не
трогая. Занятая клетка не перезаписывается никогда.

ОБЩИЙ НОМЕР. Номер, стоящий у двух и более РАЗНЫХ фамилий одного предприятия,
личным не считается: это линия отдела. Не выбрасываем — помечаем.

Запуск: python p25_vlit_lyudey.py <файл-на-дропе.csv> [--apply]
"""
import csv
import io
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict

P25 = r'C:\seostat\data\p25.db'
ОБМЕН = r'C:\seostat\drop\drop-storage'
ПОТОК = r'C:\seostat\drop\p25_vlito_lyudey.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv
ИМЯ = next((а for а in sys.argv[1:] if а.lower().endswith('.csv')), '')

ДОБАВОЧНЫЙ = re.compile(r'(?:доб|вн|ext)\.?\s*(\d{1,5})\s*$', re.I)


def номер_и_добавочный(з):
    """Добавочный отрезаем ДО чистки от знаков: иначе он слипается с номером
    (`+849550593332424` — это 8 (495) 505-93-33 доб. 2424)."""
    с = str(з or '').strip()
    доб = ''
    м = ДОБАВОЧНЫЙ.search(с)
    if м:
        доб = м.group(1)
        с = с[:м.start()]
    ц = re.sub(r'\D', '', с)
    if len(ц) == 10:
        ц = '7' + ц
    if len(ц) == 11 and ц[0] == '8':
        ц = '7' + ц[1:]
    return ('+' + ц if len(ц) == 11 and ц[0] == '7' else ''), доб


def main():
    if not ИМЯ:
        print('нужно: p25_vlit_lyudey.py <файл.csv> [--apply]')
        return
    путь = os.path.join(ОБМЕН, ИМЯ)
    if not os.path.exists(путь):
        print('НЕТ ФАЙЛА:', путь)
        return
    сыр = io.open(путь, encoding='utf-8-sig', errors='replace').read()
    первая = сыр.splitlines()[0] if сыр.strip() else ''
    раздел = ';' if первая.count(';') >= первая.count(',') else ','
    строки = list(csv.DictReader(io.StringIO(сыр), delimiter=раздел))
    print(f'файл {ИМЯ}: разделитель {раздел!r}, строк {len(строки)}')

    цб = sqlite3.connect(P25, timeout=30)
    наши = {str(r[0]) for r in цб.execute('SELECT inn FROM company')}
    поля_p = [r[1] for r in цб.execute('PRAGMA table_info(person)')]
    поля_c = [r[1] for r in цб.execute('PRAGMA table_info(contact)')]
    есть_люди = {}
    for инн, ч, тел in цб.execute(
            "SELECT inn, COALESCE(person,''), COALESCE(phone,'') FROM person"):
        есть_люди.setdefault(str(инн), {})[
            ' '.join(str(ч).split()).casefold()] = str(тел)
    номер_чей = defaultdict(set)
    for инн, зн, ч in цб.execute(
            "SELECT inn, COALESCE(value,''), COALESCE(person,'') FROM contact "
            "WHERE kind='phone'"):
        номер_чей[(str(инн), номер_и_добавочный(зн)[0])].add(
            ' '.join(str(ч).split()).casefold())

    стат = Counter()
    к_записи = []
    # фамилии на номер ВНУТРИ ЭТОГО ЖЕ файла: линия отдела видна сразу
    в_файле = defaultdict(set)
    for р in строки:
        т, _ = номер_и_добавочный(р.get('telefon'))
        ч = ' '.join(str(р.get('chelovek') or '').split())
        if т and ч:
            в_файле[(str(р.get('inn') or '').strip(), т)].add(
                ч.split()[0].casefold())

    for р in строки:
        инн = re.sub(r'\D', '', str(р.get('inn') or ''))
        чел = ' '.join(str(р.get('chelovek') or '').split())
        ссылка = str(р.get('ssylka') or '').strip()
        дата = str(р.get('data_nablyudeniya') or '').strip()
        цитата = str(р.get('citata') or '').strip()
        тел, доб = номер_и_добавочный(р.get('telefon'))
        стат['строк в файле'] += 1
        if инн not in наши:
            стат['ОТКЛОНЕНО: ИНН не из наших 491'] += 1
            continue
        if len(чел.split()) < 2:
            стат['ОТКЛОНЕНО: не ФИО'] += 1
            continue
        if not ссылка:
            стат['ОТКЛОНЕНО: нет ссылки на первоисточник'] += 1
            continue
        свежесть = 'дата есть' if дата else 'ДАТА НЕ ОПРЕДЕЛЕНА (в меру не идёт)'
        стат[свежесть] += 1
        общий = ''
        if тел:
            чужие = ((номер_чей.get((инн, тел), set()) | в_файле.get((инн, тел), set()))
                     - {чел.casefold(), чел.split()[0].casefold()})
            if чужие:
                общий = 'линия отдела: номер у нескольких фамилий'
                стат['номер общий — личным не считаю'] += 1
        был = есть_люди.get(инн, {}).get(чел.casefold())
        исход = 'завести человека'
        if был is not None:
            был_ц = re.sub(r'\D', '', был)
            нов_ц = re.sub(r'\D', '', тел)
            if not нов_ц or был_ц == нов_ц:
                исход = 'только наблюдение (человек и номер уже есть)'
            elif not был_ц:
                исход = 'ДОПИСАТЬ номер в пустую клетку'
            else:
                исход = 'ВТОРОЙ номер, старый не трогаю'
        стат[исход] += 1
        к_записи.append({
            'ishod': исход, 'inn': инн, 'person': чел, 'phone': тел,
            'dob': доб, 'obshchiy': общий,
            'post': str(р.get('dolzhnost') or '').strip(),
            'dept': str(р.get('podrazdelenie') or '').strip(),
            'email': str(р.get('pochta') or '').strip(),
            'role': str(р.get('rol') or '').strip(),
            'url': ссылка, 'date': дата, 'quote': цитата[:900],
            'file': ИМЯ})

    print(json.dumps(dict(стат.most_common()), ensure_ascii=False, indent=1))
    for з in к_записи[:12]:
        print(f"  {з['inn']} {з['person'][:30]:30} {з['phone'] or '—':16} "
              f"{з['role'][:10]:10} {з['ishod'][:28]}")
    if not ПРИМЕНИТЬ:
        print('\nСУХОЙ ПРОГОН, ничего не записано')
        цб.close()
        return

    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    до_p = цб.execute('SELECT COUNT(*) FROM person').fetchone()[0]
    до_c = цб.execute('SELECT COUNT(*) FROM contact').fetchone()[0]
    до_s = цб.execute('SELECT COUNT(*) FROM contact_source').fetchone()[0]
    дописано = 0

    def вставить(табл, поля, зн):
        имена = [к for к in поля if к in зн]
        цб.execute(f"INSERT OR IGNORE INTO {табл} ({','.join(имена)}) "
                   f"VALUES ({','.join('?' * len(имена))})",
                   [зн[к] for к in имена])

    for з in к_записи:
        источник = f"{з['file']}"
        # НАБЛЮДЕНИЕ — всегда, даже если человек уже есть: копим провенанс
        цб.execute(
            "INSERT OR IGNORE INTO contact_source(inn, contact_value, person, "
            "source, source_url, date_observed, quote, added_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (з['inn'], з['phone'] or з['email'], з['person'], источник,
             з['url'], з['date'], з['quote'], ts))
        if з['ishod'].startswith('ДОПИСАТЬ') and з['phone']:
            до_u = цб.total_changes
            цб.execute(
                "UPDATE person SET phone=?, source=COALESCE(NULLIF(source,''),?),"
                " source_url=COALESCE(NULLIF(source_url,''),?),"
                " data_podtverzhdeniya=COALESCE(NULLIF(data_podtverzhdeniya,''),?),"
                " chem_podtverzhdena=COALESCE(NULLIF(chem_podtverzhdena,''),?)"
                " WHERE inn=? AND person=? AND COALESCE(phone,'')=''",
                (з['phone'], источник, з['url'], з['date'], з['quote'][:200],
                 з['inn'], з['person']))
            дописано += цб.total_changes - до_u
        вставить('person', поля_p, {
            'inn': з['inn'], 'person': з['person'], 'position': з['post'],
            'role': з['role'], 'phone': з['phone'], 'email': з['email'],
            'source': источник, 'source_url': з['url'],
            'data_podtverzhdeniya': з['date'],
            'chem_podtverzhdena': з['quote'][:200],
            'is_tech': 1 if '1 круг' in з['role'] or '2 круг' in з['role'] else 0})
        if з['phone']:
            вставить('contact', поля_c, {
                'inn': з['inn'], 'kind': 'phone', 'value': з['phone'],
                'person': з['person'], 'role': з['role'], 'position': з['post'],
                'phone_type': ('общий' if з['obshchiy'] else 'личный'),
                'source': источник, 'source_url': з['url'],
                'data_podtverzhdeniya': з['date'],
                'chem_podtverzhdena': з['quote'][:200],
                'is_tech': 1 if '1 круг' in з['role'] or '2 круг' in з['role'] else 0,
                'is_unknown_owner': 0})
        if з['email']:
            вставить('contact', поля_c, {
                'inn': з['inn'], 'kind': 'email', 'value': з['email'],
                'person': з['person'], 'role': з['role'],
                'source': источник, 'source_url': з['url'],
                'data_podtverzhdeniya': з['date']})
    цб.commit()
    стало_p = цб.execute('SELECT COUNT(*) FROM person').fetchone()[0]
    стало_c = цб.execute('SELECT COUNT(*) FROM contact').fetchone()[0]
    стало_s = цб.execute('SELECT COUNT(*) FROM contact_source').fetchone()[0]
    техмоб = цб.execute(
        "SELECT COUNT(DISTINCT inn) FROM contact WHERE kind='phone' "
        "AND COALESCE(is_tech,0)=1 AND COALESCE(phone_type,'')='личный' "
        "AND value LIKE '+79%'").fetchone()[0]
    цб.close()

    with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
        for з in к_записи:
            ф.write(json.dumps({**з, 'ts': ts}, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())

    print(f'\nperson:  {до_p} → {стало_p}')
    print(f'contact: {до_c} → {стало_c}')
    print(f'НАБЛЮДЕНИЙ contact_source: {до_s} → {стало_s}')
    print(f'номер дописан в пустую клетку: {дописано}')
    print(f'ПРЕДПРИЯТИЙ с техническим и ЛИЧНЫМ мобильным: {техмоб}')


if __name__ == '__main__':
    main()
