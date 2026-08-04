# -*- coding: utf-8 -*-
"""Вернуть добавочные, которые приёмка отрезала и выбросила.

ЗАЧЕМ. Замер 3-й сессии: городской С ДОБАВОЧНЫМ — прямой стол человека, а не
коммутатор, и это единственный практический путь к главному инженеру, потому
что личного мобильного у него в открытой сети почти не бывает. У неё таких 16,
у меня 0 — не потому, что их нет во входных файлах (там 94), а потому, что моя
таблица не имела колонки, и разобранный добавочный уходил в никуда.

ЧТО ДЕЛАЮ: завожу колонку, прохожу файлы соседок и проставляю добавочный тем
контактам, которые уже влиты. Номер не трогаю — дописываю только то, что
потерялось.

Запуск: python p25_dobavochnye_vernut.py [--apply]
"""
import csv, io, json, os, re, sqlite3, sys, time
from collections import Counter
P25 = r'C:\seostat\data\p25.db'
ОБМЕН = r'C:\seostat\drop\drop-storage'
ПОТОК = r'C:\seostat\drop\p25_dobavochnye.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv
ДОБАВОЧНЫЙ = re.compile(r'(?:доб|вн|ext)\.?\s*(\d{1,5})\s*$', re.I)
СЛУЖЕБНЫЙ = re.compile(r'ne-podtverzhdeno|zona-ne-nasha|obshchie|spornaya', re.I)

def номер_и_доб(з):
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

цб = sqlite3.connect(P25, timeout=30)
поля = {r[1] for r in цб.execute('PRAGMA table_info(contact)')}
if 'dobavochnyy' not in поля:
    if ПРИМЕНИТЬ:
        цб.execute('ALTER TABLE contact ADD COLUMN dobavochnyy TEXT')
        цб.commit()
        print('колонка dobavochnyy заведена')
    else:
        print('колонки dobavochnyy нет — будет заведена при --apply')

стат = Counter(); правки = []
for имя in sorted(os.listdir(ОБМЕН)):
    if not (имя.startswith(('P25-LYUDI', 'P25-OBRATNYY')) and имя.endswith('.csv')):
        continue
    if СЛУЖЕБНЫЙ.search(имя):
        continue
    сыр = io.open(os.path.join(ОБМЕН, имя), encoding='utf-8-sig', errors='replace').read()
    перв = сыр.splitlines()[0] if сыр.strip() else ''
    раз = ';' if перв.count(';') >= перв.count(',') else ','
    for р in csv.DictReader(io.StringIO(сыр), delimiter=раз):
        тел, доб = номер_и_доб(р.get('telefon'))
        if not (тел and доб):
            continue
        инн = re.sub(r'\D', '', str(р.get('inn') or ''))
        стат['в файлах: номеров с добавочным'] += 1
        правки.append((инн, тел, доб, имя))

if ПРИМЕНИТЬ and 'dobavochnyy' in {r[1] for r in цб.execute('PRAGMA table_info(contact)')}:
    до = цб.total_changes
    for инн, тел, доб, файл in правки:
        цб.execute("UPDATE contact SET dobavochnyy=? WHERE inn=? AND value=? "
                   "AND COALESCE(dobavochnyy,'')=''", (доб, инн, тел))
    цб.commit()
    стат['ПРОСТАВЛЕНО добавочных'] = цб.total_changes - до
    стат['контактов с добавочным стало'] = цб.execute(
        "SELECT COUNT(*) FROM contact WHERE COALESCE(dobavochnyy,'')<>''").fetchone()[0]
    with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
        for инн, тел, доб, файл in правки:
            ф.write(json.dumps({'inn': инн, 'tel': тел, 'dob': доб, 'file': файл},
                               ensure_ascii=False) + '\n')
        ф.flush(); os.fsync(ф.fileno())
цб.close()
for з in правки[:6]:
    print(f'   {з[0]} {з[1]} доб. {з[2]}')
print()
for к, v in sorted(стат.items()):
    print(f'{к:44} {v:6}')
print('' if ПРИМЕНИТЬ else 'СУХОЙ ПРОГОН')
