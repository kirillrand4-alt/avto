# -*- coding: utf-8 -*-
"""Прицельный обратный ход по ОДНОМУ человеку: собрать вход и отдать каналу.

Владелец спросил про конкретного человека. По базам его нет — значит надо добыть.
Прибор кладёт одну строку во вход канала (`3s_p25_obratnyy_vhod.csv`) в том же формате,
что и массовый прогон: `inn;predpriyatie;fio;dolzhnost;otkuda`, разделитель «;» и
utf-8-sig — как штатный `p25_obratnyy_vhod.py` (несовпадение разделителя уже стоило мне
одного пустого прогона).

Пишет ТОЛЬКО вход. Сам прогон запускается отдельно, чтобы было видно, что именно ушло
в поисковый пул: пул общий на три сессии, и тратить его вслепую нельзя.

Запуск: python3 p25_odin_chelovek_obratnyy.py "ИНН" "Предприятие" "ФИО" ["должность"]
"""
import csv
import io
import json
import sys

VHOD = r'C:\sender\_ops\3s_p25_obratnyy_vhod.csv'

if len(sys.argv) < 4:
    print('нужно: ИНН, предприятие, ФИО')
    raise SystemExit(2)
inn, pred, fio = sys.argv[1], sys.argv[2], sys.argv[3]
dolzh = sys.argv[4] if len(sys.argv) > 4 else ''

with io.open(VHOD, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['inn', 'predpriyatie', 'fio', 'dolzhnost', 'otkuda'],
                       delimiter=';')
    w.writeheader()
    w.writerow({'inn': inn, 'predpriyatie': pred, 'fio': fio, 'dolzhnost': dolzh,
                'otkuda': 'прицельный запрос владельца'})

print('во вход записана одна строка:')
print('  ИНН %s | %s | %s | %s' % (inn, pred, fio, dolzh or '(должность неизвестна)'))
print('ИТОГ ' + json.dumps({'файл': VHOD, 'строк': 1}, ensure_ascii=False))
