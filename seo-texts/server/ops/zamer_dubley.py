# -*- coding: utf-8 -*-
"""Замер дублей фактов (находка 3-й сессии) перед починкой.

Она увидела на экране: одно заключение ЭПБ показано дважды — раз «тип не
установлен», раз «центробежная». Проверяю её числа сам и смотрю, ЧЕМ дубли
отличаются: если только типом — схлопывание безопасно, если ещё и источником
или датой, это разные документы и трогать нельзя.
"""
import os, re, sqlite3
from collections import Counter, defaultdict
ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
всего = цб.execute('SELECT COUNT(*) FROM fact').fetchone()[0]
группы = defaultdict(list)
for rid, инн, цит, тип, мод, ист, у, дата, ст in цб.execute(
        "SELECT rowid, inn, COALESCE(quote,''), COALESCE(equipment_type,''), "
        "COALESCE(model,''), COALESCE(source,''), COALESCE(source_url,''), "
        "COALESCE(event_date,''), COALESCE(status,'') FROM fact"):
    ц = re.sub(r'\s+', ' ', str(цит)).strip().lower()
    if len(ц) < 25:
        continue
    группы[(str(инн), ц)].append((rid, тип, мод, ист, у, дата, ст))
дубли = {k: v for k, v in группы.items() if len(v) > 1}
строк_в_дублях = sum(len(v) for v in дубли.values())
разн_тип = сколько_ист = сколько_дата = сколько_модель = 0
for k, v in дубли.items():
    if len({x[1] for x in v}) > 1: разн_тип += 1
    if len({x[3] for x in v}) > 1: сколько_ист += 1
    if len({x[5] for x in v}) > 1: сколько_дата += 1
    if len({x[2] for x in v}) > 1: сколько_модель += 1
print(f'фактов всего: {всего}')
print(f'групп «один ИНН + одна цитата» с повтором: {len(дубли)}')
print(f'строк внутри таких групп: {строк_в_дублях} '
      f'({100*строк_в_дублях//max(всего,1)}% базы), лишних: {строк_в_дублях-len(дубли)}')
print(f'  из групп: разный ТИП {разн_тип}, разная МОДЕЛЬ {сколько_модель}, '
      f'разный ИСТОЧНИК {сколько_ист}, разная ДАТА {сколько_дата}')
# пример
for k, v in list(дубли.items())[:2]:
    print(f'\nпример ИНН {k[0]}: {len(v)} строк, цитата «{k[1][:70]}…»')
    for rid, тип, мод, ист, у, дата, ст in v[:4]:
        print(f'   тип=«{тип[:34]}» модель=«{мод[:16]}» ист={ист[:26]} дата={дата}')
цб.close()
