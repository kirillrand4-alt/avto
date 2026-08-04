# -*- coding: utf-8 -*-
"""Применить разметку мусора к базе — и ПЕРЕСМОТРЕТЬ ею же свои старые скрытия фактов.

ПОЧЕМУ ДВА ДЕЙСТВИЯ, А НЕ ОДНО. Разметку я посчитала и выложила файлом, но в базе не менялось
ничего — карточки как захламляли обзор, так и захламляют. При этом в `hidden_item` уже лежат
19 248 моих скрытий фактов, поставленных СТАРЫМ правилом («центробежность не доказана ни
разметкой, ни текстом»). То самое правило и ошибалось: оно не знало ни про «центробежный
вентилятор», ни про «здание цеха разделения воздуха». Значит применять новое, не пересмотрев
старое, — это оставить в базе решения, про которые уже известно, что часть из них неверна.

Поэтому здесь считаются ОБА направления:
  ДОБАВИТЬ  — факты, которые новое правило признаёт мусором, а скрытия на них нет;
  СНЯТЬ     — факты, скрытые старым правилом, которые новое признаёт НАШЕЙ МАШИНОЙ или
              ПРИЗНАКОМ ПРОИЗВОДСТВА. Это возврат доказательств, а не косметика.

Скрытие факта обратимо и в панели уже показано человеку («Убрано вами: N — включите галочку,
чтобы вернуть»), поэтому механизм берётся существующий, а не изобретается новый. Причина
пишется так, чтобы её было видно и отличить от чужой: назван и модуль, и конкретный признак.

Аргументы: PRIMENIT — писать в базу; без него только счёт.
"""
import collections
import csv
import importlib.util
import io
import json
import os
import sqlite3
import sys
import urllib.request

spec = importlib.util.spec_from_file_location('mf', r'C:\sender\_ops\3s_musor_faktov.py')
mf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mf)

PRIMENIT = 'PRIMENIT' in sys.argv
sale = sqlite3.connect(r'C:\seostat\data\centro_sales.db')
sale.execute('attach database ? as f', (r'C:\seostat\data\centrifugal.db',))

# Уже скрытые факты: ключ скрытия — value, туда кладётся id факта строкой.
skryto = {}
for rid, val, reason in sale.execute(
        "select rowid, coalesce(value,''), coalesce(reason,'') from hidden_item "
        "where kind='fact'"):
    skryto[val] = (rid, reason)

dobavit, snyat = [], []
sch = collections.Counter()
for fid, inn, tip, quote in sale.execute(
        "select id, coalesce(inn,''), coalesce(equipment_type,''), coalesce(quote,'') "
        "from f.fact"):
    vid, pochemu = mf.razobrat(quote, tip)
    est = skryto.get(str(fid))
    musor = mf.svorachivat(vid)
    sch[vid] += 1
    if musor and not est:
        dobavit.append({'inn': inn, 'value': str(fid), 'vid': vid, 'pochemu': pochemu,
                        'citata': quote[:200]})
    elif not musor and est:
        # Скрыто старым правилом, а новое говорит «оставить». Возвращаем только то, что
        # новое правило признаёт машиной или признаком производства: «ничего не сказано» и
        # «текста нет» трогать незачем — там основание скрытия было другим.
        # МАРКА ВОЗВРАЩАЕТ ФАКТ НАРАВНЕ СО СЛОВОМ, включая газовую. Газовая марка — настоящая
        # центробежная машина на настоящем предприятии; то, что среда не наша, понижает
        # приоритет, а не прячет доказательство. Слово владельца: разделять, а не отсеивать.
        if vid in (mf.VID_NASH, mf.VID_PRIZNAK, mf.VID_NASH_PO_MARKE, mf.VID_MARKA_SREDA,
                   mf.VID_MARKA_GAZ):
            snyat.append({'rowid': est[0], 'inn': inn, 'value': str(fid), 'vid': vid,
                          'staraya_prichina': est[1][:120], 'pochemu': pochemu,
                          'citata': quote[:200]})

itog = {'фактов': sum(sch.values()), 'по_видам': dict(sch.most_common()),
        'скрытий_фактов_сейчас': len(skryto),
        'ДОБАВИТЬ_скрытий': len(dobavit),
        'СНЯТЬ_скрытий_вернуть_доказательства': len(snyat),
        'снять_по_видам': dict(collections.Counter(z['vid'] for z in snyat)),
        'примeneno': False}

if PRIMENIT:
    PRICH = ('мусор в карточке: {vid} — {pochemu} '
             '(правило musor_faktov, 3-я сессия, обратимо)')
    sale.executemany(
        "insert into hidden_item (inn, kind, value, reason, username, created_at) "
        "values (?, 'fact', ?, ?, 'admin', datetime('now'))",
        [(z['inn'], z['value'], PRICH.format(vid=z['vid'], pochemu=z['pochemu'])[:300])
         for z in dobavit])
    if snyat:
        sale.executemany('delete from hidden_item where rowid = ?',
                         [(z['rowid'],) for z in snyat])
    sale.commit()
    itog['примeneno'] = True
    itog['скрытий_фактов_стало'] = sale.execute(
        "select count(*) from hidden_item where kind='fact'").fetchone()[0]
    # Бэкап обоих списков — без него снятое не восстановить, в hidden_item истории нет.
    for imya, dannye, polya in (
            ('VAZHNOE-3s-SVERNUTO-musor.csv', dobavit, ['inn', 'value', 'vid', 'pochemu',
                                                        'citata']),
            ('VAZHNOE-3s-VOZVRASHCHENO-fakty.csv', snyat,
             ['rowid', 'inn', 'value', 'vid', 'staraya_prichina', 'pochemu', 'citata'])):
        if not dannye:
            continue
        b = io.StringIO()
        w = csv.DictWriter(b, fieldnames=polya, delimiter=';', extrasaction='ignore')
        w.writeheader()
        w.writerows(dannye)
        telo = b.getvalue().encode('utf-8-sig')
        req = urllib.request.Request(
            os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
            + '/' + imya, data=telo, method='PUT',
            headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', ''),
                     'Content-Type': 'text/csv'})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                itog[imya] = f'{r.status}, {len(telo)} байт'
        except Exception as e:  # noqa: BLE001
            itog[imya] = f'НЕ выгружено: {type(e).__name__}'

for z in snyat[:40]:
    print('REC ' + json.dumps({k: z[k] for k in ('inn', 'vid', 'citata')}, ensure_ascii=False))
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
