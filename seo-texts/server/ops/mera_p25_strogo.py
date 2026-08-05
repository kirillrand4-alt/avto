# -*- coding: utf-8 -*-
"""Мера ТЗ по P25: технарём делает ДОЛЖНОСТЬ, а не роль из карточки закупки.

ЧТО БЫЛО СЛОМАНО. Мера считала признак по строке «должность + роль». В `role`
у людей с tender.pro лежит «по техническим вопросам» — роль, которую человеку
дала процедура. Из-за этого мера подскочила с 1 до 5, и все четверо новых
оказались: «Специалист по устойчивому развитию», «Руководитель направления
Строительство» и трое с ПУСТОЙ должностью. Данные записаны правильно — сломан
был измеритель.

ПРАВИЛО: технарём делает должность, названная предприятием. Роль из карточки
засчитывается только если это наш канонический круг («1 круг», «технический
круг»), а не текст процедуры.
"""
import re, sqlite3
from collections import Counter
ТЕХ = ('инженер','механик','энергетик','технич','производств','кипиа','метролог','технолог')
СНАБЖ = ('материально-техническ','снабжени','закупк','омтс','логистик','бухгалтер','склад')
КРУГ = ('1 круг', '2 круг', 'технический круг')
ИЗ_ЗАПРОСА = re.compile(r'контактн\w* лиц|консультаци|по\s+(?:\w+\s+){0,2}вопрос|'
                        r'для уточнени|ответственн\w*\s+за|обращат|уточнени', re.I)

цб = sqlite3.connect(r'file:C:\seostat\data\p25.db?mode=ro', uri=True)
тех = {}
c = Counter()
for и, чел, поз, роль in цб.execute(
        "SELECT inn, COALESCE(person,''), COALESCE(position,''), COALESCE(role,'') "
        "FROM person"):
    поз, роль = str(поз), str(роль)
    низ_п = поз.casefold()
    по_должности = (any(x in низ_п for x in ТЕХ)
                    and not any(x in низ_п for x in СНАБЖ)
                    and not ИЗ_ЗАПРОСА.search(поз))
    по_кругу = роль.casefold() in КРУГ
    if по_должности or по_кругу:
        тех[(str(и), str(чел).casefold())] = (поз, роль)
        c['технарь по должности' if по_должности else 'технарь по канону круга'] += 1
    elif ИЗ_ЗАПРОСА.search(f'{поз} {роль}') and any(x in f'{поз} {роль}'.casefold()
                                                    for x in ТЕХ):
        c['роль «по техническим вопросам» — НЕ технарь'] += 1

фирмы = {}
for и, чел, зн, не in цб.execute(
        "SELECT inn, COALESCE(person,''), COALESCE(value,''), "
        "COALESCE(nomer_ne_lichnyy,'') FROM contact WHERE COALESCE(kind,'')='phone'"):
    ц = ''.join(x for x in str(зн) if x.isdigit())[-10:]
    к = (str(и), str(чел).casefold())
    if len(ц) == 10 and ц[0] == '9' and not не and к in тех:
        фирмы.setdefault(str(и), []).append((чел, тех[к][0] or тех[к][1], зн))
всего = цб.execute('SELECT COUNT(*) FROM company').fetchone()[0]
цб.close()

print('ЗАКРЫТЫЕ ПО МЕРЕ ТЗ:')
for и, сп in фирмы.items():
    for ч, д, т in сп:
        print(f'   {и:12} {str(ч)[:26]:26} {str(д)[:28]:28} {т}')
print()
print('=== ЧИСЛА ===')
for к, v in sorted(c.items()):
    print(f'   {к:44} {v:5}')
print(f'   {"технических людей всего":44} {len(тех):5}')
print(f'   {"предприятий закрыто по ТЗ":44} {len(фирмы):5} из {всего}')

# --- СТРОГАЯ МЕРА (согласована с 3-й сессией 05.08) --------------------------
# Закрытием считаем предприятие, у которого есть техническая ДОЛЖНОСТЬ, личный
# мобильный И положительная формула источника при отсутствии формулы отказа.
# Агрегатор первоисточником НЕ считается: проба 3-й сессии по 45 карточкам дала
# «с сайта предприятия номер на странице 14 из 14, с агрегатора 94 из ~130»,
# плюс два прямых разрыва. Номер с агрегатора — юрлица, не человека.
АГРЕГАТОРЫ = ('checko.ru', 'rusprofile', 'list-org', 'zachestnyibiznes', 'sbis.ru',
              'audit-it', 'e-ecolog', 'vypiska-nalog', 'kartoteka', 'seldon',
              'synapsenet', 'sparkinterfax')
ОТКАЗЫ = ('не первоисточник', 'не сайт предприятия', 'не карточка', 'не раскрытие',
          'непринят', 'не подтвержд', 'спорная привязка', 'выставочный или социальный')

цб2 = sqlite3.connect(r'file:C:\seostat\data\p25.db?mode=ro', uri=True)
набл = {}
try:
    for и, зн, url, ист in цб2.execute(
            'SELECT inn, COALESCE(contact_value,""), COALESCE(source_url,""), '
            'COALESCE(source,"") FROM contact_source'):
        ц = ''.join(x for x in str(зн) if x.isdigit())[-10:]
        набл.setdefault((str(и), ц), []).append((str(url), str(ист)))
except Exception as e:  # noqa: BLE001
    print('   наблюдений не прочитал:', str(e)[:70])
цб2.close()


def _годен(записи):
    for url, ист in записи:
        текст = (url + ' ' + ист).casefold()
        if any(о in текст for о in ОТКАЗЫ):
            continue
        if not url.startswith('http'):
            continue
        if any(а in url.casefold() for а in АГРЕГАТОРЫ):
            continue
        return True
    return False


строго, разбор = {}, Counter()
for и, сп in фирмы.items():
    for ч, д, т in сп:
        ц = ''.join(x for x in str(т) if x.isdigit())[-10:]
        з = набл.get((и, ц), [])
        if not з:
            разбор['наблюдения по номеру нет'] += 1
        elif _годен(з):
            строго.setdefault(и, []).append((ч, д, т))
            разбор['источник годен'] += 1
        else:
            разбор['агрегатор или отказ в источнике'] += 1
print(f'   {"ЗАКРЫТО СТРОГО (источник годен)":44} {len(строго):5} из {всего}')
print('   разбор строк: ' + ', '.join(f'{к}={v}' for к, v in разбор.most_common()))
