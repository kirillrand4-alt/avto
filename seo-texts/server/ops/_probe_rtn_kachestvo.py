# -*- coding: utf-8 -*-
"""Выборочная проверка: к тем ли предприятиям привязаны люди из графиков РТН.

За ночь в базу ушло 567 человек из графиков. Две проверки уже поймали по
дефекту — вложение имён и колонка «Предприятие, должность». Третья проверка
смотрит на РЕЗУЛЬТАТ: берём записанных людей и печатаем рядом название
компании из нашей базы и название организации, как оно стоит в документе.
Расхождение видно глазом сразу.

Ничего не пишет.
"""
import io
import json
import sys
from collections import Counter

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\server\ops')
import enrich_db as EDB   # noqa: E402
import rtn_znaniya as RTN  # noqa: E402

ИСТ = 'РТН: проверка знаний'
cx = EDB.EnrichDB().cx

# организация из документа по ссылке+ФИО — из потока новейшего разбора
записи = {}
for ln in io.open(RTN.П_СТРОКИ, encoding='utf-8', errors='replace'):
    try:
        d = json.loads(ln)
    except Exception:  # noqa: BLE001
        continue
    ф = d.get('файл') or ''
    е = записи.get(ф)
    if е is None or (d.get('разбор_вер') or 0) >= (е.get('разбор_вер') or 0):
        записи[ф] = d
орг_по_фио = {}
for ф, d in записи.items():
    for с in (d.get('строки') or []):
        орг_по_фио.setdefault((с.get('фио') or '').lower(),
                              с.get('организация') or '')

люди = cx.execute(
    "SELECT p.inn, p.person, COALESCE(p.post,''), COALESCE(p.role,''), "
    "COALESCE(c.name,''), COALESCE(c.region,''), COALESCE(p.source_url,'') "
    'FROM people p LEFT JOIN companies c ON c.inn = p.inn '
    'WHERE p.source = ? ORDER BY p.rowid', (ИСТ,)).fetchall()

ТЕХ = set(EDB.EnrichDB.TECH_ROLES)
роли = Counter(r[3] for r in люди)
образцы = []
шаг = max(1, len(люди) // 14)
for r in люди[::шаг][:14]:
    образцы.append({
        'inn': r[0], 'фио': r[1][:32], 'должность': r[2][:44], 'роль': r[3],
        'КОМПАНИЯ_В_БАЗЕ': r[4][:58], 'регион': r[5][:22],
        'ОРГАНИЗАЦИЯ_В_ДОКУМЕНТЕ': (орг_по_фио.get(r[1].lower()) or '?')[:58],
    })

print(json.dumps({
    'людей_из_РТН_в_базе': len(люди),
    'из_них_технических': sum(1 for r in люди if r[3] in ТЕХ),
    'предприятий': len({r[0] for r in люди}),
    'роли': роли.most_common(10),
    'выборка_каждый_%d-й' % шаг: образцы,
}, ensure_ascii=False, indent=1)[:6000])
