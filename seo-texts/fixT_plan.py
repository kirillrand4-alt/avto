# -*- coding: utf-8 -*-
r"""fixT (14.10, локально, только чтение данных): план замены 29 компаний с УСПЕШНОЙ сделкой Meyer («Meyer: клиент» /
«Meyer привлечение успешно»; владелец 14.10: «таких не надо в панель») – тем же конвейером fixQ (`fixQ_plan.py`),
только со своим списком на удаление, меткой базы и датой. Резерв – проверенные «покупатели» оценщиков P2, которых fixQ
не взял; новое правило отбора (в fixQ_plan, пометка fixT): нет ни активной, ни успешной сделки Meyer.

    python3 -E -P fixT_plan.py <папка fix/T> <папка fixK> <выход plan.json>

В папке T: fixT-ubrat.json (29: inn, menedzher, prichina), osn/db0 и osn/kodroot (свежий снимок:
`fixT_zapusk.py fixQ_vzyat.py fixT-1410-`), dadata_q.json (данные Q + свежий DaData по резерву), sverka.json,
checko_razbor.json, bitrix/, dl/fixS-bitrix-0910.zip (ссылки на папку Q).
"""
import os
import runpy
import sys

ZDES = os.path.dirname(os.path.abspath(__file__))
T = sys.argv[1]
os.environ.update({
    'FIXQ_UBRAT': os.path.join(T, 'fixT-ubrat.json'),
    'FIXQ_DATA': '14.10.2026',
    'FIXQ_BAZA': 'База 7 (замена 14.10)',
    'FIXQ_BAZA_OPIS': ('MEYER-7: замена 14.10 вместо компаний с успешной сделкой Meyer (клиент / успешное привлечение – '
                       'владелец: «таких не надо в панель»); каждая проверена оценщиками: покупатель; сделок Meyer в работе '
                       'и успешных нет'),
    'FIXQ_GRUPPA': 'gT-',
    'FIXQ_VERDIKT_VSEM': '0',
    'FIXQ_STROGO': '1',            # «не хуже текущего разброса» – без бесплатного допуска коридоров
    'FIXQ_ASSIGNED_BY': ('База 7 (замена 14.10, fixT): вместо компаний с успешной сделкой Meyer – столько же, холдинги и '
                         'домашние регионы'),
})
sys.argv = [os.path.join(ZDES, 'fixQ_plan.py')] + sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
