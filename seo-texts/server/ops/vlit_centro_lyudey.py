# -*- coding: utf-8 -*-
"""Люди 3-й сессии в центробежку: 818 строк, что не подошли к P25.

Она оставила мне два файла. По P25 из них наши только 114 строк, а 818 —
предприятия ВТОРОЙ базы владельца, центробежки: 201 технарь, 40 с личным
мобильным на 4 предприятиях. Отложить их как «не мои» значило бы выбросить
работу соседки из-за того, что я смотрел не в ту базу.

ЗАСЛОНЫ ТЕ ЖЕ, что и в P25:
  * фамилия должна быть похожа на фамилию;
  * должность и роль — врозь; признак технаря ставится по должности;
  * общий номер помечается, а не удаляется (колонка заводится, если её нет);
  * источник и ссылка пишутся на каждую строку.

Запуск: python vlit_centro_lyudey.py [--apply]
"""
import csv, io, json, os, re, sqlite3, sys, time
from collections import Counter, defaultdict

ОБМЕН = r'C:\seostat\drop\drop-storage'
ФАЙЛЫ = ('DLYA-1S-LYUDI-BEZ-KARTOCHKI.csv', 'DLYA-1S-LYUDI-K-KARTOCHKAM-KOTORYE-EST.csv')
ПОТОК = r'C:\seostat\drop\centro_prinyato_3s.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv
ТЕХ = ('инженер','механик','энергетик','технич','производств','кипиа','метролог',
       'технолог','сварщик','асу')
СНАБЖ = ('материально-техническ','снабжени','закупк','омтс','логистик','бухгалтер','склад')
НЕ_ФАМИЛИЯ = {'уважаемый','уважаемая','контактное','лицо','отдел','служба','фио','тел'}
СОМНЕНИЕ = re.compile(r'СПОРН\w*|не подтвержд\w*|сомнительн\w*|привязка не доказана', re.I)


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


путь = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
цб = sqlite3.connect(путь, timeout=30)
поля_p = {r[1] for r in цб.execute('PRAGMA table_info(person)')}
поля_c = {r[1] for r in цб.execute('PRAGMA table_info(contact)')}
наши = {str(и) for и, in цб.execute('SELECT inn FROM company')}
if 'nomer_ne_lichnyy' not in поля_c and ПРИМЕНИТЬ:
    цб.execute('ALTER TABLE contact ADD COLUMN nomer_ne_lichnyy TEXT')
    цб.commit()
    поля_c.add('nomer_ne_lichnyy')
    print('колонка nomer_ne_lichnyy заведена в centrifugal.contact')

стат = Counter()
к_записи = []
for имя in ФАЙЛЫ:
    for р in csv.DictReader(io.open(os.path.join(ОБМЕН, имя), encoding='utf-8-sig',
                                    errors='replace'), delimiter=';'):
        инн = ''.join(x for x in str(р.get('inn') or '') if x.isdigit())
        if инн not in наши:
            стат['не центробежка — пропуск'] += 1
            continue
        if any(СОМНЕНИЕ.search(str(v) or '') for v in р.values()):
            стат['ОТКЛОНЕНО: помечено сомнение'] += 1
            continue
        чел = чисто(р.get('chelovek'))
        if len(чел.split()) < 2 or чел.split()[0].casefold() in НЕ_ФАМИЛИЯ:
            стат['ОТКЛОНЕНО: имя не похоже на ФИО'] += 1
            continue
        долж = чисто(р.get('dolzhnost'))
        роль = чисто(р.get('rol'))
        низ = f'{долж} {роль}'.casefold()
        тех = 1 if (долж and any(x in низ for x in ТЕХ)
                    and not any(x in низ for x in СНАБЖ)) else 0
        личный = норм(р.get('lichnyy_nomer'))
        почта = чисто(р.get('pochta')).lower()
        прочие = [норм(x) for x in re.split(r'[|,;]', str(р.get('nomera_predpriyatiya') or ''))]
        прочие = [x for x in прочие if x and x != личный]
        if not личный and not почта and not прочие:
            стат['ОТКЛОНЕНО: ни номера, ни почты'] += 1
            continue
        стат['ПРИНЯТО'] += 1
        if тех:
            стат['   технарь по должности'] += 1
        if личный:
            стат['   с личным номером'] += 1
        к_записи.append({'inn': инн, 'person': чел, 'position': долж, 'role': роль,
                         'is_tech': тех, 'lichnyy': личный, 'pochta': почта,
                         'obshchie': прочие[:6],
                         'url': чисто(р.get('ssylka_na_cheloveka')),
                         'source': f'3-я сессия, {имя}: '
                                   + чисто(р.get('istochnik_cheloveka'))[:70]})

print('=== ЧИСЛА ===')
for к, v in sorted(стат.items()):
    print(f'   {к:44} {v:5}')
print(f'   {"к записи":44} {len(к_записи):5}')
if not ПРИМЕНИТЬ:
    print('СУХОЙ ПРОГОН')
    цб.close()
    raise SystemExit

ts = time.strftime('%Y-%m-%dT%H:%M:%S')
до = [цб.execute(f'SELECT COUNT(*) FROM {т}').fetchone()[0] for т in ('person', 'contact')]
for з in к_записи:
    пол = {'inn': з['inn'], 'person': з['person'], 'position': з['position'],
           'role': з['role'], 'phone': з['lichnyy'], 'email': з['pochta'],
           'is_tech': з['is_tech'], 'source': з['source'], 'source_url': з['url']}
    им = [к for к in пол if к in поля_p]
    цб.execute(f"INSERT OR IGNORE INTO person ({','.join(им)}) "
               f"VALUES ({','.join('?' * len(им))})", [пол[к] for к in им])
    пары = ([('phone', з['lichnyy'], '')] if з['lichnyy'] else []) \
        + ([('email', з['pochta'], '')] if з['pochta'] else []) \
        + [('phone', x, 'номер предприятия из файла 3-й сессии, не личный')
           for x in з['obshchie']]
    for вид, значение, не in пары:
        стб = {'inn': з['inn'], 'person': з['person'] if not не else '',
               'kind': вид, 'value': значение, 'source': з['source'],
               'source_url': з['url'], 'is_tech': з['is_tech'] if not не else 0}
        if не and 'nomer_ne_lichnyy' in поля_c:
            стб['nomer_ne_lichnyy'] = не
        им_c = [к for к in стб if к in поля_c]
        цб.execute(f"INSERT OR IGNORE INTO contact ({','.join(им_c)}) "
                   f"VALUES ({','.join('?' * len(им_c))})", [стб[к] for к in им_c])
цб.commit()
после = [цб.execute(f'SELECT COUNT(*) FROM {т}').fetchone()[0] for т in ('person', 'contact')]
цб.close()
with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
    for з in к_записи:
        ф.write(json.dumps({**з, 'ts': ts}, ensure_ascii=False) + '\n')
    ф.flush(); os.fsync(ф.fileno())
print()
print(f'   person:  {до[0]} → {после[0]}')
print(f'   contact: {до[1]} → {после[1]}')
