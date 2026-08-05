# -*- coding: utf-8 -*-
"""Сторож: имена колонок беру из PRAGMA, а не из головы (трижды ошибся за смену)."""
import io, json, os, sqlite3, sys, time, urllib.request
from collections import Counter
ТЕХ = ('инженер','механик','энергетик','технич','производств','кипиа','метролог','технолог')
СНАБЖ = ('материально-техническ','снабжени','закупк','омтс','мтс ','логистик','бухгалтер','склад')

# разбор tender.pro
П = r'C:\seostat\drop\tp_razbor_lyudey.jsonl'
n = люд = стел = сдолж = 0
for s in io.open(П, encoding='utf-8', errors='replace'):
    s = s.strip()
    if not s:
        continue
    n += 1
    try:
        з = json.loads(s)
    except Exception:
        continue
    for л in (з.get('lyudi') or []):
        люд += 1
        стел += 1 if str(л.get('telefon') or '').strip() else 0
        сдолж += 1 if str(л.get('dolzhnost') or '').strip() else 0
молчит = int(time.time() - os.path.getmtime(П))

цб = sqlite3.connect(r'file:C:\seostat\data\p25.db?mode=ro', uri=True)
поля_p = {r[1] for r in цб.execute('PRAGMA table_info(person)')}
поля_c = {r[1] for r in цб.execute('PRAGMA table_info(contact)')}
p = {т: цб.execute(f'SELECT COUNT(*) FROM {т}').fetchone()[0]
     for т in ('person','contact','contact_source','company')}
# ТЕХНАРЁМ ДЕЛАЕТ ДОЛЖНОСТЬ, А НЕ РОЛЬ. Сторож считал признак по строке
# «должность + роль» и печатал 10 из 491 там, где строгая мера даёт 4: в `role`
# у людей с площадки лежит «по техническим вопросам» — роль в процедуре, а не
# место работы. Мера исправлена час назад, а сторож продолжал печатать старое.
_ИЗ_ЗАПРОСА = __import__('re').compile(
    r'контактн\w* лиц|консультаци|по\s+(?:\w+\s+){0,2}вопрос|для уточнени|'
    r'ответственн\w*\s+за|обращат', __import__('re').I)
_КРУГ = ('1 круг', '2 круг', 'технический круг')
тех = {}
for и, чел, поз, роль in цб.execute(
        "SELECT inn, COALESCE(person,''), COALESCE(position,''), COALESCE(role,'') "
        "FROM person"):
    поз, роль = str(поз), str(роль)
    низ = поз.casefold()
    по_должности = (поз and any(x in низ for x in ТЕХ)
                    and not any(x in низ for x in СНАБЖ)
                    and not _ИЗ_ЗАПРОСА.search(поз))
    if по_должности or роль.casefold() in _КРУГ:
        тех[(str(и), str(чел).casefold())] = поз or роль
фирмы = {}
for и, чел, зн, не in цб.execute(
        "SELECT inn, COALESCE(person,''), COALESCE(value,''), "
        "COALESCE(nomer_ne_lichnyy,'') FROM contact WHERE COALESCE(kind,'')='phone'"):
    ц = ''.join(c for c in str(зн) if c.isdigit())[-10:]
    к = (str(и), str(чел).casefold())
    if len(ц) == 10 and ц[0] == '9' and not не and к in тех:
        фирмы[str(и)] = (str(чел), тех[к], str(зн))
видели = {(str(и), str(з)) for и, з in
          цб.execute("SELECT inn, COALESCE(contact_value,'') FROM contact_source")}
без = sum(1 for и, з in цб.execute("SELECT inn, COALESCE(value,'') FROM contact")
          if (str(и), str(з)) not in видели)
цб.close()

службы = {}
for порт in (8012, 8014):
    try:
        службы[порт] = urllib.request.urlopen(f'http://127.0.0.1:{порт}/', timeout=8).getcode()
    except Exception as e:
        службы[порт] = getattr(e, 'code', None) or f'НЕТ ({type(e).__name__})'

print('ЗАКРЫТЫЕ ПО ТЗ:')
for и, (ч, д, т) in фирмы.items():
    print(f'   {и:12} {ч[:28]:28} {д[:24]:24} {т}')
print()
print('=== ЧИСЛА ===')
print(f'разбор tender.pro: карточек {n} из 314 | людей {люд} | с телефоном {стел} '
      f'| с должностью {сдолж} | молчит {молчит} с')
print(f'p25: person {p["person"]} | contact {p["contact"]} | наблюдений '
      f'{p["contact_source"]} | предприятий {p["company"]}')
print(f'p25: технических людей {len(тех)} | контактов без наблюдения {без}')
print(f'p25: по ТЗ (технарь + личный мобильный) {len(фирмы)} из {p["company"]}')
print(f'службы: 8012 -> {службы[8012]} | 8014 -> {службы[8014]}')
