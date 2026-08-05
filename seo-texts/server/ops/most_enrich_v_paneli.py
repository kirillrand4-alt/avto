# -*- coding: utf-8 -*-
"""Мостик: люди из enrich.db в базы панелей, иначе добытое не видно продавцу.

ЧТО ВСКРЫЛОСЬ. Обход руководства пишет людей в `enrich.db.people`, а панели
читают свои базы: 8012 — `centrifugal.db.person`, 8014 — `p25.db.person`.
Мостика не было. Замер:

    P25          522 человека enrich нет в базе панели, из них технарей 172,
                 с личным мобильным 8
    центробежка  902 человека нет, технарей 54, с личным мобильным 1

Девять технических руководителей с личными мобильными добыты, лежат и не видны
тому, кто звонит. Это тот же класс, что «починка не дошла до пользователя»,
только ценой в готовые контакты.

ЗАСЛОНЫ ПРЕЖНИЕ: признак технаря только по должности (роль из карточки закупки
им не считается); номер, помеченный не личным, переносится с пометкой;
источник и ссылка пишутся на каждую строку; наблюдение — где есть таблица.

Запуск: python most_enrich_v_paneli.py [--apply]
"""
import io, json, os, re, sqlite3, sys, time
from collections import Counter
sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB

ПОТОК = r'C:\seostat\drop\most_enrich_v_paneli.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv
ТЕХ = ('инженер','механик','энергетик','технич','производств','кипиа','метролог',
       'технолог','сварщик','асу')
СНАБЖ = ('материально-техническ','снабжени','закупк','омтс','логистик','бухгалтер','склад')
ИЗ_ЗАПРОСА = re.compile(r'контактн\w* лиц|консультаци|по\s+(?:\w+\s+){0,2}вопрос|'
                        r'для уточнени|ответственн\w*\s+за|обращат', re.I)
НЕ_ФАМИЛИЯ = {'уважаемый','уважаемая','контактное','лицо','отдел','служба','фио','тел'}

db = EDB.EnrichDB()
поля_e = {r[1] for r in db.cx.execute('PRAGMA table_info(people)')}
есть_роль = 'role' in поля_e
люди = list(db.cx.execute(
    "SELECT inn, COALESCE(person,''), COALESCE(post,''), " +
    ("COALESCE(role,'')" if есть_роль else "''") +
    ", COALESCE(phone,''), COALESCE(email,''), COALESCE(nomer_ne_lichnyy,''), "
    "COALESCE(source_url,''), COALESCE(source,'') FROM people"))

базы = {}
for имя, путь in (('P25', r'C:\seostat\data\p25.db'),
                  ('центробежка', os.getenv('CENTRIFUGAL_DB')
                   or r'C:\seostat\data\centrifugal.db')):
    цб = sqlite3.connect(путь, timeout=30)
    базы[имя] = {'cx': цб,
                 'инны': {str(и) for и, in цб.execute('SELECT inn FROM company')},
                 'есть': {(str(и), str(ч).casefold()) for и, ч in
                          цб.execute("SELECT inn, COALESCE(person,'') FROM person")},
                 'p': {r[1] for r in цб.execute('PRAGMA table_info(person)')},
                 'c': {r[1] for r in цб.execute('PRAGMA table_info(contact)')},
                 'набл': bool(цб.execute("SELECT name FROM sqlite_master WHERE "
                                         "type='table' AND name='contact_source'").fetchone())}

стат = Counter()
к_записи = []
for и, чел, пост, роль, тел, почта, нл, урл, ист in люди:
    и, чел, пост = str(и), str(чел).strip(), str(пост).strip()
    if len(чел.split()) < 2 or чел.split()[0].casefold() in НЕ_ФАМИЛИЯ:
        стат['ОТКЛОНЕНО: имя не похоже на ФИО'] += 1
        continue
    if not str(тел).strip() and not str(почта).strip():
        стат['ОТКЛОНЕНО: ни номера, ни почты'] += 1
        continue
    низ = пост.casefold()
    тех = 1 if (пост and any(x in низ for x in ТЕХ)
                and not any(x in низ for x in СНАБЖ)
                and not ИЗ_ЗАПРОСА.search(пост)) else 0
    for имя_б, б in базы.items():
        if и not in б['инны'] or (и, чел.casefold()) in б['есть']:
            continue
        стат[f'{имя_б}: к переносу'] += 1
        if тех:
            стат[f'{имя_б}:   технарь по должности'] += 1
        к_записи.append({'baza': имя_б, 'inn': и, 'person': чел, 'position': пост,
                         'role': str(роль)[:80], 'phone': str(тел), 'email': str(почта),
                         'is_tech': тех, 'ne_lichnyy': str(нл),
                         'url': str(урл), 'source': str(ист)[:90] or 'enrich.db'})

print('=== ЧИСЛА ===')
for к, v in sorted(стат.items()):
    print(f'   {к:44} {v:6}')
print(f'   {"к переносу всего":44} {len(к_записи):6}')
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
           'role': з['role'], 'phone': з['phone'], 'email': з['email'],
           'is_tech': з['is_tech'], 'source': з['source'], 'source_url': з['url']}
    им = [к for к in пол if к in б['p']]
    б['cx'].execute(f"INSERT OR IGNORE INTO person ({','.join(им)}) "
                    f"VALUES ({','.join('?' * len(им))})", [пол[к] for к in им])
    for вид, значение in (('phone', з['phone']), ('email', з['email'])):
        if not str(значение).strip():
            continue
        стб = {'inn': з['inn'], 'person': з['person'], 'kind': вид, 'value': значение,
               'source': з['source'], 'source_url': з['url'], 'is_tech': з['is_tech']}
        if з['ne_lichnyy'] and 'nomer_ne_lichnyy' in б['c']:
            стб['nomer_ne_lichnyy'] = з['ne_lichnyy']
        им_c = [к for к in стб if к in б['c']]
        б['cx'].execute(f"INSERT OR IGNORE INTO contact ({','.join(им_c)}) "
                        f"VALUES ({','.join('?' * len(им_c))})", [стб[к] for к in им_c])
        if б['набл']:
            б['cx'].execute(
                "INSERT OR IGNORE INTO contact_source(inn, contact_value, person, "
                "source, source_url, date_observed, quote, added_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (з['inn'], значение, з['person'], з['source'], з['url'], '', '', ts))
for б in базы.values():
    б['cx'].commit()
print()
for и, б in базы.items():
    п = [б['cx'].execute('SELECT COUNT(*) FROM person').fetchone()[0],
         б['cx'].execute('SELECT COUNT(*) FROM contact').fetchone()[0]]
    print(f'   {и}: person {до[и][0]} → {п[0]} | contact {до[и][1]} → {п[1]}')
    б['cx'].close()
with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
    for з in к_записи:
        ф.write(json.dumps({**з, 'ts': ts}, ensure_ascii=False) + '\n')
    ф.flush(); os.fsync(ф.fileno())
