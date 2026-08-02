# -*- coding: utf-8 -*-
"""Сверка разбора с исходным документом: не съехали ли колонки.

Новый разбор поднял выход в двадцать раз, и прежде чем 1000+ записей уйдут в
базу, надо посмотреть глазами на ОДИН файл целиком: текст документа рядом с
тем, что из него извлеклось. Систематический сдвиг колонок выглядит правдоподобно
в отчёте и виден только при такой сверке.
"""
import io
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\server\ops')
import enrich_contacts as EC   # noqa: E402
import rtn_znaniya as RTN      # noqa: E402

# берём запись нового разбора с наибольшим числом строк
лучшая = None
for ln in io.open(RTN.П_СТРОКИ, encoding='utf-8', errors='replace'):
    try:
        d = json.loads(ln)
    except Exception:  # noqa: BLE001
        continue
    if not d.get('разбор_вер'):
        continue
    # берём файл из ПОСЛЕДНЕГО пополнения потока: сверять надо то, что
    # разобрано только что, а не давно проверенное
    if (лучшая is None
            or (d.get('разбор_вер') or 0) > (лучшая.get('разбор_вер') or 0)
            or ((d.get('разбор_вер') or 0) == (лучшая.get('разбор_вер') or 0)
                and len(d.get('строки') or []) > len(лучшая.get('строки') or []))):
        лучшая = d

if not лучшая:
    print(json.dumps({'ошибка': 'записей нового разбора ещё нет'},
                     ensure_ascii=False))
    raise SystemExit

т = EC.doc_text(лучшая['файл']) or ''
т = re.sub(r'[ \t\u00a0]+', ' ', т)
строки_док = [s.strip() for s in т.split('\n') if s.strip()][:46]

print(json.dumps({
    'файл': лучшая['файл'],
    'извлечено_строк': len(лучшая.get('строки') or []),
    'первые_46_строк_документа': строки_док,
    'первые_6_записей': (лучшая.get('строки') or [])[:6],
    'последние_2_записи': (лучшая.get('строки') or [])[-2:],
}, ensure_ascii=False, indent=1)[:5200])
