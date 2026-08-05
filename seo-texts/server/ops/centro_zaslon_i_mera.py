# -*- coding: utf-8 -*-
"""Центробежка: заслон общих номеров и мера ТЗ по должности.

Те же два правила, что уже стоят в enrich и p25:
  один номер у 2+ людей предприятия — не личный;
  один номер у 2+ предприятий — не принадлежит и предприятию.
Технарём делает ДОЛЖНОСТЬ, а не роль из карточки закупки.
"""
import os, re, sqlite3, sys, time
from collections import Counter, defaultdict
ТЕХ = ('инженер','механик','энергетик','технич','производств','кипиа','метролог',
       'технолог','сварщик','асу')
СНАБЖ = ('материально-техническ','снабжени','закупк','омтс','логистик','бухгалтер','склад')
ИЗ_ЗАПРОСА = re.compile(r'контактн\w* лиц|консультаци|по\s+(?:\w+\s+){0,2}вопрос|'
                        r'для уточнени|ответственн\w*\s+за|обращат', re.I)
ПРИМЕНИТЬ = '--apply' in sys.argv
путь = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
цб = sqlite3.connect(путь, timeout=30)
люди = defaultdict(set); фирмы_н = defaultdict(set); строки = []
for rid, инн, чел, зн, вид in цб.execute(
        "SELECT rowid, inn, COALESCE(person,''), COALESCE(value,''), COALESCE(kind,'') "
        "FROM contact"):
    if str(вид) and str(вид) != 'phone':
        continue
    ц = ''.join(c for c in str(зн) if c.isdigit())[-10:]
    if len(ц) < 6:
        continue
    ч = str(чел).strip().casefold()
    if ч:
        люди[(str(инн), ц)].add(ч)
    фирмы_н[ц].add(str(инн))
    строки.append((rid, str(инн), ч, ц))
метки = []
c = Counter()
for rid, инн, ч, ц in строки:
    if len(фирмы_н[ц]) >= 2:
        метки.append((rid, 'номер стоит у %d разных предприятий' % len(фирмы_н[ц])))
        c['помечено: номер у разных предприятий'] += 1
    elif len(люди.get((инн, ц), ())) >= 2:
        метки.append((rid, 'номер делят %d человека предприятия' % len(люди[(инн, ц)])))
        c['помечено: делят люди предприятия'] += 1
    else:
        c['номер уникален'] += 1
if ПРИМЕНИТЬ:
    for rid, не in метки:
        цб.execute('UPDATE contact SET nomer_ne_lichnyy=? WHERE rowid=?', (не, rid))
    цб.commit()

тех = {}
for и, чел, поз, роль in цб.execute(
        "SELECT inn, COALESCE(person,''), COALESCE(position,''), COALESCE(role,'') "
        "FROM person"):
    низ = str(поз).casefold()
    if (поз and any(x in низ for x in ТЕХ) and not any(x in низ for x in СНАБЖ)
            and not ИЗ_ЗАПРОСА.search(str(поз))):
        тех[(str(и), str(чел).casefold())] = str(поз)
фирмы = {}
for и, чел, зн, не in цб.execute(
        "SELECT inn, COALESCE(person,''), COALESCE(value,''), "
        "COALESCE(nomer_ne_lichnyy,'') FROM contact WHERE COALESCE(kind,'')='phone'"):
    ц = ''.join(x for x in str(зн) if x.isdigit())[-10:]
    к = (str(и), str(чел).casefold())
    if len(ц) == 10 and ц[0] == '9' and not не and к in тех:
        фирмы.setdefault(str(и), []).append((чел, тех[к], зн))
всего = цб.execute('SELECT COUNT(*) FROM company').fetchone()[0]
цб.close()
print('=== ЧИСЛА, ЦЕНТРОБЕЖКА ===')
for к, v in sorted(c.items()):
    print(f'   {к:44} {v:6}')
print(f'   {"технических людей по должности":44} {len(тех):6}')
print(f'   {"ПРЕДПРИЯТИЙ по ТЗ (технарь + мобильный)":44} {len(фирмы):6} из {всего}')
print()
for и, сп in list(фирмы.items())[:10]:
    ч, д, т = сп[0]
    print(f'   {и:12} {str(ч)[:26]:26} {str(д)[:26]:26} {т}')
