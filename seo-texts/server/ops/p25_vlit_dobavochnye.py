# -*- coding: utf-8 -*-
"""Приёмка 35 добавочных от 3-й сессии — с ПЕРЕСЧИТАННЫМ признаком «прямой стол».

ЧТО НЕ ТАК С ЯРЛЫКОМ. В сопроводительном письме 3-я сессия пишет, что поймала
себя на ошибке: `8 (495) 664-88-40 доб. 2794` она приняла за прямой стол
снабженца, а это линия ЭТП ГПБ. Но в САМОМ ФАЙЛЕ эта строка по-прежнему помечена
«ПРЯМОЙ СТОЛ» — ярлык отстал от её же поправки. Таких строк 4 из 35: базовый
номер там делят несколько человек, то есть по её собственному определению это
линия, а не стол.

ПОЭТОМУ ПРИЗНАК СЧИТАЮ САМ, из данных: базовый номер, встреченный у двух и более
разных людей, прямым столом быть не может. Ярлык сохраняю рядом — видно, где он
разошёлся с данными.

Запуск: python p25_vlit_dobavochnye.py [--apply]
"""
import csv, io, json, os, re, sqlite3, sys, time
from collections import Counter, defaultdict

P25 = r'C:\seostat\data\p25.db'
ОБМЕН = r'C:\seostat\drop\drop-storage'
ИМЯ = 'P25-DOBAVOCHNYE-3S-001.csv'
ПОТОК = r'C:\seostat\drop\p25_dobavochnye_prinyato.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv
СОМНЕНИЕ = re.compile(r'СПОРН\w*|спорная привязка|не подтвержд\w*|сомнительн\w*|'
                      r'НЕ ПРОВЕРЕН\w*|привязка не доказана', re.I)


def чисто(з):
    return ' '.join(str(з or '').split())


сыр = io.open(os.path.join(ОБМЕН, ИМЯ), encoding='utf-8-sig', errors='replace').read()
строки = list(csv.DictReader(io.StringIO(сыр), delimiter=';'))
люди_на_базовом = defaultdict(set)
for р in строки:
    б = ''.join(c for c in чисто(р.get('telefon')) if c.isdigit())[-10:]
    if len(б) >= 6:
        люди_на_базовом[б].add(чисто(р.get('chelovek')).casefold())

цб = sqlite3.connect(P25, timeout=30)
поля_c = {r[1] for r in цб.execute('PRAGMA table_info(contact)')}
есть_доб = 'dobavochnyy' in поля_c
есть_чем = 'chem_podtverzhdena' in поля_c
стат = Counter()
к_записи = []
for р in строки:
    инн = re.sub(r'\D', '', чисто(р.get('inn')))
    чел = чисто(р.get('chelovek'))
    тел = чисто(р.get('telefon'))
    доб = re.sub(r'\D', '', чисто(р.get('dobavochnyy')))
    ярлык = чисто(р.get('vid'))
    ссылка = чисто(р.get('ssylka'))
    если_сомнение = any(СОМНЕНИЕ.search(str(v) or '') for v in р.values())
    if если_сомнение:
        стат['ОТКЛОНЕНО: в строке помечено сомнение'] += 1
        continue
    if not (инн and чел and тел):
        стат['ОТКЛОНЕНО: нет ИНН, человека или номера'] += 1
        continue
    б = ''.join(c for c in тел if c.isdigit())[-10:]
    делят = len(люди_на_базовом.get(б, ())) >= 2
    прямой_ярлык = 'ПРЯМОЙ' in ярлык.upper()
    вид = ('линия с добавочными: базовый номер стоит у %d человек'
           % len(люди_на_базовом[б]) if делят else 'прямой стол')
    if прямой_ярлык and делят:
        стат['ЯРЛЫК ИСПРАВЛЕН: помечен столом, а базовый делят'] += 1
    стат['принято: прямой стол' if not делят else 'принято: линия с добавочными'] += 1
    к_записи.append({'inn': инн, 'chelovek': чел, 'telefon': тел, 'dob': доб,
                     'vid': вид, 'yarlyk_3s': ярлык[:40], 'ssylka': ссылка,
                     'dolzhnost': чисто(р.get('dolzhnost'))})

for к, v in sorted(стат.items()):
    print(f'   {к:52} {v:4}')

if not ПРИМЕНИТЬ:
    print('СУХОЙ ПРОГОН, к записи', len(к_записи))
    цб.close()
    raise SystemExit

ts = time.strftime('%Y-%m-%dT%H:%M:%S')
до = цб.total_changes
новых = 0
for з in к_записи:
    поля = ['inn', 'person', 'kind', 'value', 'source', 'source_url']
    зн = [з['inn'], з['chelovek'], 'phone', з['telefon'],
          f"3-я сессия: {з['vid']}", з['ssylka']]
    if есть_доб:
        поля.append('dobavochnyy'); зн.append(з['dob'])
    if есть_чем:
        поля.append('chem_podtverzhdena')
        зн.append(f"добавочный {з['dob']}; {з['vid']}")
    try:
        цб.execute(f"INSERT OR IGNORE INTO contact ({', '.join(поля)}) "
                   f"VALUES ({', '.join('?' * len(поля))})", зн)
        новых += 1
    except sqlite3.Error as e:
        стат[f'сбой вставки: {type(e).__name__}'] += 1
цб.commit()
всего = цб.execute('SELECT COUNT(*) FROM contact').fetchone()[0]
с_доб = цб.execute("SELECT COUNT(*) FROM contact WHERE COALESCE(dobavochnyy,'')<>''"
                   ).fetchone()[0] if есть_доб else -1
цб.close()

with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
    for з in к_записи:
        ф.write(json.dumps({**з, 'ts': ts}, ensure_ascii=False) + '\n')
    ф.flush(); os.fsync(ф.fileno())

print()
print(f'вставок выполнено            {новых:5}')
print(f'контактов в p25 стало        {всего:5}')
print(f'из них с добавочным          {с_доб:5}')
