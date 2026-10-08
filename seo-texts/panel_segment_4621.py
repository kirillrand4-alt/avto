# -*- coding: utf-8 -*-
"""Оптовики зерна (основной ОКВЭД 46.21*) -> сегмент «1 экспортёры» (владелец 08.10: «отнеси»).
Три компании Базы 4 остались без сегмента после перевода сегмента на основной ОКВЭД
(fixE1): кода 46.21 не было в таблице ОКВЭД -> сегмент. Теперь он в `okved_segment_tz.json`.
segment и segment_osn = «1 экспортёры», popadanie = «основной ОКВЭД»; сегменты по доп.
ОКВЭД остаются в segment_dop, прежние значения – в *_ishodnyy/_ishodnoe (fixE1).
Журнал «было/стало» – на дроп. Одна транзакция; откат – по журналу."""
import io, json, os, sqlite3, time
KAT = r'C:\centro2\data\meyer_baza1.db'
DROP = r'C:\seostat\drop\drop-storage'
SEG = '1 экспортёры'
k = sqlite3.connect(KAT, timeout=60)
k.row_factory = sqlite3.Row
zhurnal = []
with k:
    for r in k.execute("select inn, predpriyatie, okved, segment, segment_osn, popadanie from company "
                       "where okved = '46.21' or okved like '46.21.%'").fetchall():
        novoe = {'segment': SEG, 'segment_osn': SEG, 'popadanie': 'основной ОКВЭД'}
        bylo = {x: r[x] for x in novoe}
        if bylo != novoe:
            k.execute('update company set segment=?, segment_osn=?, popadanie=? where inn=?', (SEG, SEG, 'основной ОКВЭД', r['inn']))
            zhurnal.append({'inn': r['inn'], 'imya': r['predpriyatie'], 'okved': r['okved'], 'bylo': bylo, 'stalo': novoe})
put = os.path.join(DROP, time.strftime('panel-segment-4621-%Y%m%d-%H%M%S.json'))
io.open(put, 'w', encoding='utf-8').write(json.dumps(zhurnal, ensure_ascii=False, indent=1))
print('изменено:', len(zhurnal))
for z in zhurnal:
    print(z['inn'], z['imya'], z['okved'], z['bylo'], '->', z['stalo']['segment'])
print('журнал:', os.path.basename(put))
