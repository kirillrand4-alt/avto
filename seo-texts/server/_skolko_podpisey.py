# -*- coding: utf-8 -*-
r"""Сколько ролей телефонов можно снять со страниц — замер по выборке кэша.

Если подпись «Комм. отдел:» читается у заметной доли компаний, её стоит писать
не только на странице лида, а прямо в phone_contacts — тогда роль увидит и
выгрузка, и обзвон, и письма.
"""
import json
import os
import random
import sys

sys.path.insert(0, r'C:\sender')
sys.path.insert(0, r'C:\sender\sender')
import lid_ssylka as LS  # noqa: E402

КЕШ = r'C:\seostat\drop\pagecache'
файлы = [n for n in os.listdir(КЕШ) if n.endswith('.json.gz')]
random.seed(20260821)
выборка = random.sample(файлы, min(300, len(файлы)))
ст = {'компаний': 0, 'с_номерами': 0, 'номеров': 0, 'с_подписью': 0,
      'компаний_с_подписью': 0}
подписи = {}
for имя in выборка:
    инн = имя.split('.')[0]
    страницы = LS._stranicy_kesha(инн)
    if not страницы:
        continue
    ст['компаний'] += 1
    со = LS._kontakty_so_stranic(страницы)
    тел = со.get('tel') or {}
    if not тел:
        continue
    ст['с_номерами'] += 1
    есть = False
    for узел in тел.values():
        ст['номеров'] += 1
        for п in узел.get('podpisi') or []:
            ст['с_подписью'] += 1
            подписи[п[:28]] = подписи.get(п[:28], 0) + 1
            есть = True
            break
    if есть:
        ст['компаний_с_подписью'] += 1
print(json.dumps({'частые_подписи': dict(sorted(подписи.items(),
                                                key=lambda x: -x[1])[:25])},
                 ensure_ascii=False, indent=1))
print(json.dumps({'выборка': len(выборка), 'счёт': ст},
                 ensure_ascii=False, indent=1))
