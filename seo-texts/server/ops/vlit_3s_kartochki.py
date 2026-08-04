# -*- coding: utf-8 -*-
"""Приёмка файла карточек 3-й сессии: должность и метка карточки — врозь.

ЕЁ НАХОДКА ВЕРНА И ЦЕННА: контакт в карточке закупки написан словами самого
заказчика, доказывать принадлежность не нужно. Но её счёт «8 предприятий
закрыто по букве ТЗ» держится на колонке `tehnicheskiy_krug=да`, а она
выставляется по МЕТКЕ карточки («по техническим вопросам»), и в 14 строках из
27 колонка `dolzhnost_v_tekste` при этом ПУСТА.

Это ровно то, что я час назад исправил у себя: метка процедуры говорит, к кому
идти с техническим вопросом, но не говорит, кем человек работает. Поэтому:

    должность в тексте есть  → position, признак технаря ставится
    только метка карточки    → role, признак НЕ ставится
    её пометка «ОБЩИЙ»       → номер сразу помечается не личным

Ничего не выбрасываю: строки без должности принимаются как контакты с ролью.
Запуск: python vlit_3s_kartochki.py [--apply]
"""
import csv, io, json, os, re, sqlite3, sys, time
from collections import Counter

P25 = r'C:\seostat\data\p25.db'
ОБМЕН = r'C:\seostat\drop\drop-storage'
ИМЯ = 'P25-TP-KARTOCHKI-LYUDI-3S.csv'
ПОТОК = r'C:\seostat\drop\p25_prinyato_3s_kartochki.jsonl'
ПРИМЕНИТЬ = '--apply' in sys.argv
ТЕХ = ('инженер','механик','энергетик','технич','производств','кипиа','метролог',
       'технолог','сварщик','асу','кип')
СНАБЖ = ('материально-техническ','снабжени','закупк','омтс','логистик','бухгалтер','склад')
НЕ_ФАМИЛИЯ = {'уважаемый','уважаемая','контактное','лицо','отдел','служба','фио','тел'}


def чисто(з):
    return ' '.join(str(з or '').split())


def норм_тел(т):
    ц = re.sub(r'\D', '', str(т or ''))
    if len(ц) == 11 and ц[0] in '78':
        ц = '7' + ц[1:]
    elif len(ц) == 10:
        ц = '7' + ц
    else:
        return ''
    return '+' + ц


сыр = io.open(os.path.join(ОБМЕН, ИМЯ), encoding='utf-8-sig', errors='replace').read()
строки = list(csv.DictReader(io.StringIO(сыр), delimiter=';'))
цб = sqlite3.connect(P25, timeout=30)
поля_p = {r[1] for r in цб.execute('PRAGMA table_info(person)')}
поля_c = {r[1] for r in цб.execute('PRAGMA table_info(contact)')}
наши = {str(и) for и, in цб.execute('SELECT inn FROM company')}

стат = Counter()
к_записи = []
for р in строки:
    инн = re.sub(r'\D', '', чисто(р.get('inn')))
    if инн not in наши:
        стат['ИНН вне P25'] += 1
        continue
    чел = чисто(р.get('chelovek'))
    if len(чел.split()) < 2 or чел.split()[0].casefold() in НЕ_ФАМИЛИЯ:
        стат['ОТКЛОНЕНО: имя не похоже на ФИО'] += 1
        continue
    знач = чисто(р.get('znachenie'))
    вид_её = чисто(р.get('vid'))
    if not знач:
        стат['человек без контакта — пропуск'] += 1
        continue
    почта = знач.lower() if '@' in знач else ''
    тел = '' if почта else норм_тел(знач)
    if not почта and not тел:
        стат['значение не разобралось'] += 1
        continue
    должность = чисто(р.get('dolzhnost_v_tekste'))
    метка = чисто(р.get('rol_po_kartochke'))
    низ = должность.casefold()
    тех = 1 if (должность and any(x in низ for x in ТЕХ)
                and not any(x in низ for x in СНАБЖ)) else 0
    общий = 'ОБЩИЙ' in вид_её
    if должность:
        стат['должность названа в тексте'] += 1
    else:
        стат['только метка карточки — признак технаря НЕ ставлю'] += 1
    if общий:
        стат['   её заслон пометил номер общим'] += 1
    if тех and not общий:
        стат['ТЕХНАРЬ по должности, номер не общий'] += 1
    к_записи.append({
        'inn': инн, 'person': чел, 'position': должность,
        'role': метка or ('технический круг' if тех else ''),
        'phone': тел, 'email': почта, 'is_tech': тех,
        'ne_lichnyy': ('пометка 3-й сессии: ' + вид_её) if общий else '',
        'url': чисто(р.get('ssylka')), 'date': чисто(р.get('data_kartochki')),
        'quote': (чисто(р.get('osnovanie')) or чисто(р.get('predmet')))[:400],
        'source': 'tender.pro, карточка закупки (файл 3-й сессии)'
                  + (' [2–3 года]' if чисто(р.get('svezhest')) == 'устаревший' else ''),
    })

print('=== ЧИСЛА ===')
for к, v in sorted(стат.items()):
    print(f'   {к:52} {v:5}')
print(f'   {"к записи":52} {len(к_записи):5}')

if not ПРИМЕНИТЬ:
    print('СУХОЙ ПРОГОН')
    цб.close()
    raise SystemExit

ts = time.strftime('%Y-%m-%dT%H:%M:%S')
до = [цб.execute(f'SELECT COUNT(*) FROM {т}').fetchone()[0]
      for т in ('person', 'contact', 'contact_source')]
for з in к_записи:
    пол = {'inn': з['inn'], 'person': з['person'], 'position': з['position'],
           'role': з['role'], 'phone': з['phone'], 'email': з['email'],
           'is_tech': з['is_tech'], 'source': з['source'], 'source_url': з['url']}
    им = [к for к in пол if к in поля_p]
    цб.execute(f"INSERT OR IGNORE INTO person ({','.join(им)}) "
               f"VALUES ({','.join('?' * len(им))})", [пол[к] for к in им])
    for вид, значение in (('phone', з['phone']), ('email', з['email'])):
        if not значение:
            continue
        стб = {'inn': з['inn'], 'person': з['person'], 'kind': вид,
               'value': значение, 'source': з['source'], 'source_url': з['url']}
        if з['ne_lichnyy'] and 'nomer_ne_lichnyy' in поля_c:
            стб['nomer_ne_lichnyy'] = з['ne_lichnyy']
        им_c = [к for к in стб if к in поля_c]
        цб.execute(f"INSERT OR IGNORE INTO contact ({','.join(им_c)}) "
                   f"VALUES ({','.join('?' * len(им_c))})", [стб[к] for к in им_c])
        цб.execute("INSERT OR IGNORE INTO contact_source(inn, contact_value, person, "
                   "source, source_url, date_observed, quote, added_at) "
                   "VALUES(?,?,?,?,?,?,?,?)",
                   (з['inn'], значение, з['person'], з['source'], з['url'],
                    з['date'], з['quote'], ts))
цб.commit()
после = [цб.execute(f'SELECT COUNT(*) FROM {т}').fetchone()[0]
         for т in ('person', 'contact', 'contact_source')]
цб.close()
with io.open(ПОТОК, 'a', encoding='utf-8') as ф:
    for з in к_записи:
        ф.write(json.dumps({**з, 'ts': ts}, ensure_ascii=False) + '\n')
    ф.flush(); os.fsync(ф.fileno())
print()
print(f'   person:     {до[0]} → {после[0]}')
print(f'   contact:    {до[1]} → {после[1]}')
print(f'   наблюдений: {до[2]} → {после[2]}')
