# -*- coding: utf-8 -*-
"""СЛОВАРЬ, третий заход: четыре чужих семейства сидели в нём под видом наших машин.

Проверка чужими глазами (агент по слиянию словарей) нашла в моём файле то, чего мои три
заслона не ловили. Каждое — не опечатка, а целое семейство:

    ЗИФ-1    72 встречи, САМАЯ ЧАСТАЯ строка словаря — это ЗОЛОТОИЗВЛЕКАТЕЛЬНАЯ ФАБРИКА
             АО «Полюс Красноярск», площадка ОПО. Аббревиатура совпала с компрессором
             ЗИФ-ПВ, и я взяла фабрику за машину. ЗИФ2 — то же самое
    ТВ2-117А, ТВ3-117ВМ   АВИАЦИОННЫЕ турбовальные двигатели Ми-8. Префикс ТВ у меня
             означал турбовоздуходувку, а тут это турбовальный двигатель
    ТГ-1, ТГ-4, ТГ-9      ТУРБОГЕНЕРАТОРЫ, цитаты про паропроводы ЦВД/ЦНД
    К-105, К-108          АДСОРБЕРЫ и колонны НПЗ: на нефтепереработке префикс «К-»
             означает КОЛОННУ, а не компрессор

Пятое, помельче, но того же корня: `К-5/7` помечен центробежным, а в цитате «поставка
ДИЗЕЛЬНОГО компрессора ТМТ К-5».

ЧТО ДЕЛАЮ. Ставлю четвёртый заслон — по СЛОВАМ ЧУЖОГО ПРЕДМЕТА рядом с обозначением, и
пятый — по типу площадки (НПЗ/фабрика/электростанция), где префикс значит другое. Плюс
свожу написания: `ЦК-135/8` и `ЦК135/8` — одна серия, 100 из 811 строк это варианты.

Проба расширена ровно этими случаями: ЗИФ-1, ТВ2-117А, ТГ-1, К-105 ОБЯЗАНЫ быть отсеяны,
а ТВ-80-1,6, К-250-61-1, ЦК-135/8 обязаны остаться. Если проба провалится — числа внизу
недостоверны, и это печатается.
"""
import collections
import io
import json
import os
import re
import sqlite3
import urllib.request

ISTOCHNIKI = [(r'C:\seostat\data\centrifugal.db', 'fact'),
              (r'C:\seostat\drop\drop-storage\atlas_copco.db', 'tenders'),
              (r'C:\seostat\drop\drop-storage\atlas_copco.db', 'fakty')]
SERIYA = re.compile(
    r'\b((?:ТВ|ЦК|ЦНД|К|КТК|ВЦ|ЗИФ|НВЭ|ВП|ВМ|ПКС|ЭК|АК|ТГ|ГПА|АДГ|ВК|КР|УКС|ВШ|ТКА|Ц)'
    r'[- ]?\d{1,4}(?:[-/][\dА-Яа-яA-Za-z,\.]{1,8}){0,3})\b', re.U)
PRINCIP = (('центробежный', re.compile(r'центробежн|турбокомпрессор', re.I)),
           ('винтовой', re.compile(r'винтов', re.I)),
           ('поршневой', re.compile(r'поршнев', re.I)),
           ('мембранный', re.compile(r'мембранн', re.I)),
           ('дизельный привод', re.compile(r'дизельн', re.I)))
VID = (('воздуходувка', re.compile(r'воздуходув|газодув', re.I)),
       ('нагнетатель', re.compile(r'нагнетател', re.I)),
       ('ВРУ', re.compile(r'воздухоразделен|\bВРУ\b|криоген', re.I)),
       ('генератор азота', re.compile(r'генератор\w*\s+азота|азотн\w+\s+станци', re.I)),
       ('генератор кислорода', re.compile(r'генератор\w*\s+кислорода|кислородн\w+\s+станци', re.I)),
       ('МКС', re.compile(r'\bМКС\b|передвижн\w+\s+компрессор', re.I)),
       ('осушитель', re.compile(r'осушител', re.I)),
       ('ГПА', re.compile(r'газоперекачивающ|\bГПА\b', re.I)),
       ('компрессор', re.compile(r'компрессор', re.I)))

# --- заслоны --------------------------------------------------------------------------
CHUZH_MASHINA = re.compile(
    r'вентилятор|дымосос|\bнасос\w*\b|градирн|конвейер|кондиционер|трактор|сельхоз|'
    r'автотранспорт|стартер|John Deere|New Holland|MacDon|автомат\w*\s+выключател|\bIP\d\d\b',
    re.I)
CHUZH_PREDMET = re.compile(
    r'золотоизвлекательн|обогатительн\w+\s+фабрик|\bЗИФ\b\s*(?:фабрик|АО|ООО)|'
    r'турбогенератор|турбовальн|авиационн\w+\s+двигател|вертолёт|вертолет|\bМи-8\b|'
    r'адсорбер|абсорбер|ректификацион\w+\s+колонн|\bколонн\w+\b|'
    r'паропровод|\bЦВД\b|\bЦНД\b|\bтурбин\w+\b|котлоагрегат|резервуар', re.I)
POMESH = re.compile(r'здани|укрыти|помещени|цех\b|корпус|фабрик\w+\s+АО|площадк\w+\s+ОПО', re.I)
POZ = re.compile(r'поз\.?\s*$|позици\w*\s*$|№\s*$|техн\.?\s*№\s*$|зав\.?\s*№\s*$', re.I)
NASHA_RYADOM = re.compile(r'компрессор|воздуходув|нагнетател|воздухоразделен|'
                          r'генератор\w*\s+(?:азота|кислорода)|осушител', re.I)


def klyuch(s):
    """Свод написаний: ЦК-135/8 и ЦК135/8 — одна серия."""
    return re.sub(r'[\s\-]', '', s).upper().replace(',', '.')


s_ = collections.defaultdict(lambda: {'v': 0, 'p': collections.Counter(),
                                      'vid': collections.Counter(), 'inn': set(),
                                      'url': set(), 'cit': '', 'napis': set()})
snyato = collections.Counter()
for baza, tabl in ISTOCHNIKI:
    if not os.path.exists(baza):
        continue
    cx = sqlite3.connect('file:%s?mode=ro' % baza.replace('\\', '/'), uri=True)
    kol = [r[1] for r in cx.execute('pragma table_info("%s")' % tabl)]
    if not kol:
        cx.close(); continue
    pinn = 'inn' if 'inn' in kol else None
    for r in cx.execute('select %s from "%s"' % (','.join('"%s"' % k for k in kol), tabl)):
        d = dict(zip(kol, r))
        tekst = ' '.join(str(v) for v in r if v is not None)
        if len(tekst) < 8:
            continue
        for m in SERIYA.finditer(tekst):
            syr = m.group(1)
            do = tekst[max(0, m.start() - 60):m.start()]
            okno = tekst[max(0, m.start() - 130):m.end() + 130]
            if POZ.search(do):
                snyato['позиция / техн. № / зав. №'] += 1; continue
            if CHUZH_MASHINA.search(okno):
                snyato['чужая машина'] += 1; continue
            if CHUZH_PREDMET.search(okno) and not NASHA_RYADOM.search(okno):
                snyato['ЧУЖОЙ ПРЕДМЕТ (фабрика, турбогенератор, колонна, авиадвигатель)'] += 1
                continue
            if POMESH.search(okno) and not NASHA_RYADOM.search(okno):
                snyato['помещение'] += 1; continue
            k = klyuch(syr)
            z = s_[k]
            z['v'] += 1
            z['napis'].add(syr)
            for i, rg in PRINCIP:
                if rg.search(okno):
                    z['p'][i] += 1; break
            for i, rg in VID:
                if rg.search(okno):
                    z['vid'][i] += 1; break
            if pinn and str(d.get(pinn) or '').strip():
                z['inn'].add(str(d[pinn]).strip())
            for u in re.findall(r'https?://\S+', tekst)[:3]:
                z['url'].add(u)
            if not z['cit']:
                z['cit'] = re.sub(r'[\s;]+', ' ', okno)[:170]
    cx.close()

itog = {k: z for k, z in s_.items() if z['v'] >= 2}

PROBA_DOLZHNY_UYTI = ['ЗИФ-1', 'ЗИФ2', 'ТВ2-117А', 'ТВ3-117ВМ', 'ТГ-1', 'К-105', 'К-108']
PROBA_DOLZHNY_OSTATSYA = [('ТВ-80-1,6', 'воздуходувка'), ('К-250-61-1', 'компрессор'),
                          ('ЦК-135/8', 'компрессор')]
provaly = []
for s in PROBA_DOLZHNY_UYTI:
    k = klyuch(s)
    if k in itog and itog[k]['v'] > 5:
        provaly.append('%s должна быть отсеяна, осталась (%d встреч): %s'
                       % (s, itog[k]['v'], itog[k]['cit'][:90]))
for s, vd in PROBA_DOLZHNY_OSTATSYA:
    k = klyuch(s)
    if k not in itog:
        provaly.append('%s ПОТЕРЯНА' % s)
    else:
        top = (itog[k]['vid'].most_common(1) or [('?', 0)])[0][0]
        if top != vd:
            provaly.append('%s вид: ждали «%s», вышло «%s»' % (s, vd, top))

dok = [(k, z) for k, z in itog.items()
       if (z['vid'].most_common(1) or [('не установлен', 0)])[0][0] != 'не установлен']
SHAPKA = 'seriya;napisaniya;princip;vid;vstrech;innov;ssylok;ssylki;citata\n'
put = r'C:\sender\_ops\PARK-SLOVAR-SERII-3S-v3.csv'
with io.open(put, 'w', encoding='utf-8-sig') as f:
    f.write(SHAPKA)
    for k, z in sorted(dok, key=lambda x: -x[1]['v']):
        f.write(';'.join([k, ' | '.join(sorted(z['napis'])[:4]),
                          (z['p'].most_common(1) or [('не установлен', 0)])[0][0],
                          (z['vid'].most_common(1) or [('?', 0)])[0][0],
                          str(z['v']), str(len(z['inn'])), str(len(z['url'])),
                          ' | '.join(list(z['url'])[:3]),
                          z['cit'].replace(';', ',')]) + '\n')
try:
    drop = os.environ.get('DROP_URL', '').rstrip('/')
    tok = os.environ.get('DROP_TOKEN', '')
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request('%s/%s' % (drop, os.path.basename(put)),
                                 data=io.open(put, 'rb').read(), method='PUT',
                                 headers={'X-Drop-Token': tok})
    otvet = op.open(req, timeout=180).read().decode('utf-8', 'replace')[:120]
except Exception as e:  # noqa: BLE001
    otvet = 'не выложено: %s' % str(e)[:100]

print('\n\n########## ПРОБА')
for p in provaly:
    print('  ПРОВАЛ: %s' % p)
print('  провалов %d из %d' % (len(provaly),
                               len(PROBA_DOLZHNY_UYTI) + len(PROBA_DOLZHNY_OSTATSYA)))
if provaly:
    print('  ЧИСЛА НИЖЕ НЕДОСТОВЕРНЫ')

print('\n########## ЧИСЛА')
print('  серий после свода написаний   %5d  (было 811 строк, из них 100 — варианты)' % len(itog))
print('  из них с доказанным видом     %5d' % len(dok))
print('  --- сняли заслоны')
for k, v in snyato.most_common():
    print('     %-56s %5d' % (k, v))
print('  разных ИНН по доказанным      %5d' % len({i for _, z in dok for i in z['inn']}))
print('  выложено: %s' % otvet)
print('ИТОГ ' + json.dumps({'серий': len(itog), 'доказанных': len(dok),
                            'провалов': len(provaly), 'снято': dict(snyato)},
                           ensure_ascii=False))
