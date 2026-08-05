# -*- coding: utf-8 -*-
"""Список технарей на обзвон от 3-й сессии — в ту базу, где предприятие есть.

ЕЁ ФАЙЛ УЖЕ ГОТОВ К ЗВОНКУ: ИНН, человек, личный мобильный, должность,
доказательство роли и ссылка на карточку. Из 82 строк должность технаря названа
в 12, у 70 она пуста и признак держится на формулировке заказчика («по всем
техническим вопросам»). Принимаю ВСЕ, но признак технаря ставлю только там, где
названа должность — расхождение с ней записано и вынесено владельцу.

Лью в P25 или в центробежку — смотря где ИНН. Отправить строку в «не наше»
только потому, что смотрел одну базу, я уже чуть не сделал час назад.

Запуск: python vlit_obzvon_tehnari.py [--apply]
"""
import csv, io, json, os, re, sqlite3, sys, time
from collections import Counter

ОБМЕН = r'C:\seostat\drop\drop-storage'
ИМЯ = 'P25-OBZVON-TEHNARI-3S-001.csv'
ПОТОК = r'C:\seostat\drop\prinyato_obzvon_tehnari.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv
ТЕХ = ('инженер','механик','энергетик','технич','производств','кипиа','метролог',
       'технолог','сварщик','асу')
СНАБЖ = ('материально-техническ','снабжени','закупк','омтс','логистик','бухгалтер','склад')
ИЗ_ЗАПРОСА = re.compile(r'контактн\w* лиц|консультаци|по\s+(?:\w+\s+){0,2}вопрос|'
                        r'для уточнени|ответственн\w*\s+за|обращат', re.I)
НЕ_ФАМИЛИЯ = {'уважаемый','уважаемая','контактное','лицо','отдел','служба','фио','тел'}


def чисто(з):
    return ' '.join(str(з or '').split())


def норм(т):
    ц = re.sub(r'\D', '', str(т or ''))
    if len(ц) == 11 and ц[0] in '78':
        ц = '7' + ц[1:]
    elif len(ц) == 10:
        ц = '7' + ц
    else:
        return ''
    return '+' + ц


базы = {}
for имя, путь in (('P25', r'C:\seostat\data\p25.db'),
                  ('центробежка', os.getenv('CENTRIFUGAL_DB')
                   or r'C:\seostat\data\centrifugal.db')):
    цб = sqlite3.connect(путь, timeout=30)
    базы[имя] = {'cx': цб, 'путь': путь,
                 'инны': {str(и) for и, in цб.execute('SELECT inn FROM company')},
                 'p': {r[1] for r in цб.execute('PRAGMA table_info(person)')},
                 'c': {r[1] for r in цб.execute('PRAGMA table_info(contact)')},
                 'набл': bool(цб.execute("SELECT name FROM sqlite_master WHERE "
                                         "type='table' AND name='contact_source'").fetchone())}

стат = Counter()
к_записи = []
for р in csv.DictReader(io.open(os.path.join(ОБМЕН, ИМЯ), encoding='utf-8-sig',
                                errors='replace'), delimiter=';'):
    инн = ''.join(x for x in чисто(р.get('inn')) if x.isdigit())
    куда = next((и for и, б in базы.items() if инн in б['инны']), '')
    if not куда:
        стат['ИНН ни в одной базе'] += 1
        continue
    чел = чисто(р.get('chelovek'))
    if len(чел.split()) < 2 or чел.split()[0].casefold() in НЕ_ФАМИЛИЯ:
        стат['ОТКЛОНЕНО: имя не похоже на ФИО'] += 1
        continue
    тел = норм(р.get('LICHNYY_MOBILNYY'))
    if not тел:
        стат['ОТКЛОНЕНО: номер не разобрался'] += 1
        continue
    долж = чисто(р.get('dolzhnost'))
    низ = долж.casefold()
    тех = 1 if (долж and any(x in низ for x in ТЕХ)
                and not any(x in низ for x in СНАБЖ)
                and not ИЗ_ЗАПРОСА.search(долж)) else 0
    стат[f'{куда}: принято'] += 1
    стат[f'{куда}:   с должностью технаря' if тех
         else f'{куда}:   должность не названа — признак не ставлю'] += 1
    к_записи.append({'baza': куда, 'inn': инн, 'person': чел, 'position': долж,
                     'role': чисто(р.get('chem_dokazana_rol'))[:80] or 'технический круг',
                     'phone': тел, 'is_tech': тех,
                     'url': чисто(р.get('ssylka_na_kartochku')),
                     'date': чисто(р.get('data_zakupki')),
                     'quote': (чисто(р.get('osnovanie')) or
                               чисто(р.get('chem_dokazana_rol')))[:400],
                     'source': 'tender.pro, карточка закупки (список обзвона 3-й сессии)'})

print('=== ЧИСЛА ===')
for к, v in sorted(стат.items()):
    print(f'   {к:52} {v:4}')
print(f'   {"к записи":52} {len(к_записи):4}')
if not ПРИМЕНИТЬ:
    for б in базы.values():
        б['cx'].close()
    print('СУХОЙ ПРОГОН')
    raise SystemExit

ts = time.strftime('%Y-%m-%dT%H:%M:%S')
до = {и: [б['cx'].execute('SELECT COUNT(*) FROM person').fetchone()[0],
          б['cx'].execute('SELECT COUNT(*) FROM contact').fetchone()[0]]
      for и, б in базы.items()}
for з in к_записи:
    б = базы[з['baza']]
    пол = {'inn': з['inn'], 'person': з['person'], 'position': з['position'],
           'role': з['role'], 'phone': з['phone'], 'is_tech': з['is_tech'],
           'source': з['source'], 'source_url': з['url']}
    им = [к for к in пол if к in б['p']]
    б['cx'].execute(f"INSERT OR IGNORE INTO person ({','.join(им)}) "
                    f"VALUES ({','.join('?' * len(им))})", [пол[к] for к in им])
    стб = {'inn': з['inn'], 'person': з['person'], 'kind': 'phone',
           'value': з['phone'], 'source': з['source'], 'source_url': з['url'],
           'is_tech': з['is_tech']}
    им_c = [к for к in стб if к in б['c']]
    б['cx'].execute(f"INSERT OR IGNORE INTO contact ({','.join(им_c)}) "
                    f"VALUES ({','.join('?' * len(им_c))})", [стб[к] for к in им_c])
    if б['набл']:
        б['cx'].execute(
            "INSERT OR IGNORE INTO contact_source(inn, contact_value, person, source, "
            "source_url, date_observed, quote, added_at) VALUES(?,?,?,?,?,?,?,?)",
            (з['inn'], з['phone'], з['person'], з['source'], з['url'],
             з['date'], з['quote'], ts))
for б in базы.values():
    б['cx'].commit()
print()
for и, б in базы.items():
    после = [б['cx'].execute('SELECT COUNT(*) FROM person').fetchone()[0],
             б['cx'].execute('SELECT COUNT(*) FROM contact').fetchone()[0]]
    print(f'   {и}: person {до[и][0]} → {после[0]} | contact {до[и][1]} → {после[1]}')
    б['cx'].close()
with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
    for з in к_записи:
        ф.write(json.dumps({**з, 'ts': ts}, ensure_ascii=False) + '\n')
    ф.flush(); os.fsync(ф.fileno())
