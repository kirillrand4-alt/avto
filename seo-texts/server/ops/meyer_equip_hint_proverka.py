# -*- coding: utf-8 -*-
"""READ-ONLY: что попадает в «Оборудование по профилю» meyer-письма.

Для указанных ИНН берёт equip_categories / equip_by_okved из базы обзвона и
прогоняет через _equipment_hint боевого ai_letter (division='meyer'), чтобы
увидеть, какая компрессорная лексика проходит фильтр.

    meyer_equip_hint_proverka.py ИНН [ИНН ...]
    meyer_equip_hint_proverka.py seg 'Зерно, мука, элеваторы, семена'
"""
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import _equipment_hint, CROSS_LEX  # noqa: E402

ob = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=30)
ob.row_factory = sqlite3.Row
табл = [r[0] for r in ob.execute("SELECT name FROM sqlite_master WHERE type='table'")]
колонки = {}
for т in табл:
    колонки[т] = [r[1] for r in ob.execute('PRAGMA table_info("%s")' % т)]
главная = next((т for т in табл if 'inn' in колонки[т]
                and any(к.startswith('equip') for к in колонки[т])), None)
print('таблица:', главная)

инны = sys.argv[1:]
if инны and инны[0] == 'seg':
    s = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
    инны = [r[0] for r in s.execute(
        "SELECT DISTINCT inn FROM recipients WHERE segment=? AND source LIKE 'knigi-meyer%'",
        (инны[1],))][:400]

eqk = [к for к in колонки.get(главная, []) if к.startswith('equip')]
утекло = 0
всего = 0
примеры = []
for инн in инны:
    r = ob.execute('SELECT %s FROM "%s" WHERE inn=? LIMIT 1' % (
        ','.join(eqk), главная), (инн,)).fetchone()
    if not r:
        continue
    всего += 1
    сырое = r['equip_categories'] if 'equip_categories' in r.keys() and r['equip_categories'] \
        else (r['equip_by_okved'] if 'equip_by_okved' in r.keys() else '')
    hint = _equipment_hint(сырое, 'meyer')
    хиты = [name for rx, name in CROSS_LEX['meyer'] if re.search(rx, hint)]
    if хиты:
        утекло += 1
        if len(примеры) < 6:
            примеры.append((инн, str(сырое)[:220], hint[:220], хиты))
for п in примеры:
    print('ИНН', п[0])
    print('   сырое:', п[1])
    print('   hint :', п[2])
    print('   хиты :', п[3])
print('колонки equip:', eqk)
print('ИТОГ: с карточкой обзвона %d из %d, компрессорная лексика прошла фильтр у %d'
      % (всего, len(инны), утекло))
