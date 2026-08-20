# -*- coding: utf-8 -*-
r"""Сверка догруза: каждая строка CSV обязана быть в recipients и в группе.

CSV пишется с разделителем «;» (так его понимает штатный импорт) — читать его
обычным DictReader нельзя: вся строка становится одним полем, и сверка молча
показывает ноль совпадений. Проверяем не «команда не упала», а результат.
"""
import csv
import io
import json
import sqlite3

CSV_PATH = r'C:\sender\_tmp\partiya-935-dogruz.csv'
ГРУППА = 'Партия 935'
d = {}
with io.open(CSV_PATH, encoding='utf-8-sig', newline='') as f:
    ряды = list(csv.DictReader(f, delimiter=';'))
d['в_csv'] = len(ряды)

c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True, timeout=60)
c.row_factory = sqlite3.Row
нашлось = без_группы = без_инн = 0
примеры = []
for r in ряды:
    адрес = (r.get('email') or '').strip().lower()
    if not адрес:
        continue
    ряд = c.execute("select id, coalesce(inn,'') inn, coalesce(extra_json,'') ex "
                    'from recipients where lower(email)=?', (адрес,)).fetchone()
    if not ряд:
        if len(примеры) < 5:
            примеры.append({'нет_в_панели': адрес})
        continue
    нашлось += 1
    if not ряд['inn']:
        без_инн += 1
    try:
        гр = (json.loads(ряд['ex']) or {}).get('gruppy') or []
    except Exception:  # noqa: BLE001
        гр = []
    if ГРУППА not in гр:
        без_группы += 1
        if len(примеры) < 5:
            примеры.append({'без_группы': адрес, 'id': ряд['id'],
                            'ex': ряд['ex'][:80]})
d['в_группе_всего'] = c.execute(
    "select count(*) from recipients where extra_json like ?",
    ('%' + ГРУППА + '%',)).fetchone()[0]
d['всего_recipients'] = c.execute('select count(*) from recipients').fetchone()[0]
c.close()
d['нашлось_в_панели'] = нашлось
d['БЕЗ_ГРУППЫ'] = без_группы
d['без_инн'] = без_инн
d['примеры'] = примеры
print(json.dumps(d, ensure_ascii=False, indent=1))
