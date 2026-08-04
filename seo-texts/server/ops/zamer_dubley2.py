# -*- coding: utf-8 -*-
"""Какие дубли схлопывать БЕЗОПАСНО, а какие трогать нельзя.

3-я сессия предложила ключ «одинаковые inn + quote схлопывать». Замер показал,
почему так нельзя: у 2 306 групп разный ИСТОЧНИК, у 1 510 разная ДАТА. Один и
тот же текст закупки в январе и в марте — это ПОВТОРНАЯ покупка, самый ценный
сигнал для продавца, а не дубль. Схлопнув, мы сотрём «берут регулярно».

Безопасны два случая:
  А — полный повтор: совпали inn+quote+источник+дата+ссылка. Это одна строка,
      занесённая дважды;
  Б — один документ, разный разбор: совпали inn+quote+ссылка (та самая находка
      про заключение ЭПБ, показанное и «тип не установлен», и «центробежная»).
      Тут не удаляем, а ОСТАВЛЯЕМ строку с сильнейшим типом.
"""
import os, re, sqlite3
from collections import defaultdict
ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
полн = defaultdict(list); документ = defaultdict(list)
for rid, инн, цит, тип, мод, ист, у, дата in цб.execute(
        "SELECT rowid, inn, COALESCE(quote,''), COALESCE(equipment_type,''), "
        "COALESCE(model,''), COALESCE(source,''), COALESCE(source_url,''), "
        "COALESCE(event_date,'') FROM fact"):
    ц = re.sub(r'\s+', ' ', str(цит)).strip().lower()
    if len(ц) < 25:
        continue
    полн[(str(инн), ц, str(ист), str(дата), str(у))].append((rid, тип))
    if str(у).strip():
        документ[(str(инн), ц, str(у))].append((rid, тип, str(ист), str(дата)))
А = {k: v for k, v in полн.items() if len(v) > 1}
лишних_А = sum(len(v) - 1 for v in А.values())
Б = {k: v for k, v in документ.items()
     if len(v) > 1 and len({x[1] for x in v}) > 1}
строк_Б = sum(len(v) for v in Б.values())
print(f'А. ПОЛНЫЙ ПОВТОР (всё совпало): групп {len(А)}, лишних строк {лишних_А}')
print(f'Б. ОДИН ДОКУМЕНТ, РАЗНЫЙ ТИП: групп {len(Б)}, строк {строк_Б}')
неопозн = sum(1 for v in Б.values()
              for _r, т, _i, _d in v if 'не установлен' in т.lower())
print(f'   из них строк с «тип не установлен» (их и гасим): {неопозн}')
for k, v in list(Б.items())[:3]:
    print(f'\n  ИНН {k[0]} ссылка {k[2][:44]}…')
    for rid, т, ист, дата in v[:4]:
        print(f'     тип=«{т[:40]}» ист={ист[:22]} дата={дата}')
цб.close()
