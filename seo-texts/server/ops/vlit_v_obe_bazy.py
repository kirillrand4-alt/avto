# -*- coding: utf-8 -*-
"""Приёмка стандартных файлов соседок В ОБЕ БАЗЫ — по тому, где есть ИНН.

ЧТО БЫЛО СЛОМАНО. Главный приёмщик `p25_vlit_lyudey.py` знает только p25.db и
молча пропускает всё остальное. Из-за этого канал добора 3-й сессии не дал
ничего: «Паначев Дмитрий Сергеевич, главный энергетик, +7 912 582-64-70» —
ИНН 5911029807, это Уралкалий, он во ВТОРОЙ базе. Файл был выложен давно,
колонки те же, приёмщик отработал «успешно» и записал ноль.

Тот же урок я применил к одному опу два часа назад и не перенёс на главный —
починка снова не дошла до того, кто ею пользуется.

Берёт стандартную форму (inn;chelovek;dolzhnost;telefon;pochta;rol;ssylka;
citata) и льёт в ту базу, где ИНН есть. Заслоны прежние: сомнение отклоняется,
должность и роль врозь, признак технаря только по должности.

Запуск: python vlit_v_obe_bazy.py <маска> [--apply]
"""
import csv, io, json, os, re, sqlite3, sys, time
from collections import Counter

ОБМЕН = r'C:\seostat\drop\drop-storage'
ПОТОК = r'C:\seostat\drop\vlito_v_obe_bazy.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv
МАСКА = next((а for а in sys.argv[1:] if not а.startswith('--')), 'P25-DOBOR-3S-')
ТЕХ = ('инженер','механик','энергетик','технич','производств','кипиа','метролог',
       'технолог','сварщик','асу')
СНАБЖ = ('материально-техническ','снабжени','закупк','омтс','логистик','бухгалтер','склад')
ИЗ_ЗАПРОСА = re.compile(r'контактн\w* лиц|консультаци|по\s+(?:\w+\s+){0,2}вопрос|'
                        r'для уточнени|ответственн\w*\s+за|обращат', re.I)
СОМНЕНИЕ = re.compile(r'СПОРН\w*|не подтвержд\w*|сомнительн\w*|не первоисточник|'
                      r'привязка не доказана', re.I)
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
    базы[имя] = {'cx': цб,
                 'инны': {str(и) for и, in цб.execute('SELECT inn FROM company')},
                 'p': {r[1] for r in цб.execute('PRAGMA table_info(person)')},
                 'c': {r[1] for r in цб.execute('PRAGMA table_info(contact)')},
                 'набл': bool(цб.execute("SELECT name FROM sqlite_master WHERE "
                                         "type='table' AND name='contact_source'").fetchone())}

файлы = sorted(f for f in os.listdir(ОБМЕН) if f.startswith(МАСКА) and f.endswith('.csv'))
csv.field_size_limit(10 ** 7)
стат = Counter()
к_записи = []
for имя in файлы:
    for р in csv.DictReader(io.open(os.path.join(ОБМЕН, имя), encoding='utf-8-sig',
                                    errors='replace'), delimiter=';'):
        инн = ''.join(x for x in чисто(р.get('inn')) if x.isdigit())
        # ИНН БЫВАЕТ В ОБЕИХ БАЗАХ (Уралкалий есть и в P25, и в центробежке).
        # Первый вариант брал первую попавшуюся — и строка не доезжала до той
        # базы, где её ждут. Лью во все, где предприятие есть.
        куда = [и for и, б in базы.items() if инн in б['инны']]
        if not куда:
            стат['ИНН ни в одной базе'] += 1
            continue
        if any(СОМНЕНИЕ.search(str(v) or '') for v in р.values()):
            стат['ОТКЛОНЕНО: помечено сомнение'] += 1
            continue
        чел = чисто(р.get('chelovek'))
        if len(чел.split()) < 2 or чел.split()[0].casefold() in НЕ_ФАМИЛИЯ:
            стат['ОТКЛОНЕНО: имя не похоже на ФИО'] += 1
            continue
        тел = норм(р.get('telefon'))
        почта = чисто(р.get('pochta')).lower()
        if not тел and not почта:
            стат['ОТКЛОНЕНО: ни номера, ни почты'] += 1
            continue
        долж = чисто(р.get('dolzhnost'))
        низ = долж.casefold()
        тех = 1 if (долж and any(x in низ for x in ТЕХ)
                    and not any(x in низ for x in СНАБЖ)
                    and not ИЗ_ЗАПРОСА.search(долж)) else 0
        for к_ in куда:
            стат[f'{к_}: принято'] += 1
            if тех:
                стат[f'{к_}:   технарь по должности'] += 1
        ц = ''.join(x for x in тел if x.isdigit())[-10:]
        if тех and len(ц) == 10 and ц[0] == '9':
            стат['ТЕХНАРЬ + ЛИЧНЫЙ МОБИЛЬНЫЙ'] += 1
        к_записи.append({'bazy': куда, 'inn': инн, 'person': чел, 'position': долж,
                         'role': чисто(р.get('rol'))[:80], 'phone': тел,
                         'email': почта, 'is_tech': тех,
                         'url': чисто(р.get('ssylka')),
                         'date': чисто(р.get('data_nablyudeniya')),
                         'quote': чисто(р.get('citata'))[:400],
                         'source': f'3-я сессия, {имя}'})

print(f'файлов по маске {МАСКА}: {len(файлы)}')
print('=== ЧИСЛА ===')
for к, v in sorted(стат.items()):
    print(f'   {к:44} {v:5}')
print(f'   {"к записи":44} {len(к_записи):5}')
if not ПРИМЕНИТЬ:
    for б in базы.values():
        б['cx'].close()
    print('СУХОЙ ПРОГОН')
    raise SystemExit

ts = time.strftime('%Y-%m-%dT%H:%M:%S')
до = {и: [б['cx'].execute('SELECT COUNT(*) FROM person').fetchone()[0],
          б['cx'].execute('SELECT COUNT(*) FROM contact').fetchone()[0]]
      for и, б in базы.items()}
записано = Counter()
for з in к_записи:
  for _имя_б in з['bazy']:
    б = базы[_имя_б]
    _до = б['cx'].total_changes
    пол = {'inn': з['inn'], 'person': з['person'], 'position': з['position'],
           'role': з['role'], 'phone': з['phone'], 'email': з['email'],
           'is_tech': з['is_tech'], 'source': з['source'], 'source_url': з['url']}
    им = [к for к in пол if к in б['p']]
    б['cx'].execute(f"INSERT OR IGNORE INTO person ({','.join(им)}) "
                    f"VALUES ({','.join('?' * len(им))})", [пол[к] for к in им])
    for вид, значение in (('phone', з['phone']), ('email', з['email'])):
        if not значение:
            continue
        стб = {'inn': з['inn'], 'person': з['person'], 'kind': вид, 'value': значение,
               'source': з['source'], 'source_url': з['url'], 'is_tech': з['is_tech']}
        им_c = [к for к in стб if к in б['c']]
        б['cx'].execute(f"INSERT OR IGNORE INTO contact ({','.join(им_c)}) "
                        f"VALUES ({','.join('?' * len(им_c))})", [стб[к] for к in им_c])
        if б['набл']:
            б['cx'].execute(
                "INSERT OR IGNORE INTO contact_source(inn, contact_value, person, "
                "source, source_url, date_observed, quote, added_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (з['inn'], значение, з['person'], з['source'], з['url'],
                 з['date'], з['quote'], ts))
    # СЧИТАЮ ПО РЕАЛЬНЫМ ИЗМЕНЕНИЯМ, А НЕ ПО НАМЕРЕНИЮ. `INSERT OR IGNORE`
    # молча съедает нарушение любого ограничения: отчёт печатал «принято 2»,
    # а в базе не менялось ничего, и поймал я это только проверкой по фамилии.
    записано[_имя_б] += 1 if б['cx'].total_changes > _до else 0
    записано[f'{_имя_б}: строка не легла (OR IGNORE)'] += 0 if б['cx'].total_changes > _до else 1

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
