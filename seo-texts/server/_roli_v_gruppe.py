# -*- coding: utf-8 -*-
r"""Есть ли роль у адресов группы и как это соотносится с фримейлом."""
import json
import sqlite3

ФРИ = ('mail.ru', 'yandex.ru', 'ya.ru', 'gmail.com', 'bk.ru', 'inbox.ru',
       'list.ru', 'rambler.ru', 'internet.ru', 'icloud.com', 'yandex.com')
e = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
роль_адреса = {}
for инн, ем, роль in e.execute("select inn, lower(email), coalesce(role,'') "
                               'from emails'):
    роль_адреса[(str(инн), ем)] = роль
e.close()

s = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True, timeout=60)
ст = {'адресов_в_группе': 0, 'с_ролью': 0, 'роль_не_общая': 0,
      'фримейл': 0, 'фримейл_с_ролью': 0, 'новых_сегодня': 0,
      'новых_с_ролью': 0}
for ем, инн, ex, cr in s.execute(
        "select lower(coalesce(email,'')), coalesce(inn,''), "
        "coalesce(extra_json,''), coalesce(created_at,'') from recipients "
        "where extra_json like '%Партия 935%'"):
    if not ем:
        continue
    ц = ''.join(x for x in str(инн) if x.isdigit())
    ст['адресов_в_группе'] += 1
    р = роль_адреса.get((ц, ем), '')
    фри = ем.split('@')[-1] in ФРИ
    если_роль = bool(р)
    if если_роль:
        ст['с_ролью'] += 1
    if р and р not in ('общий', 'приёмная', 'общий/приёмная'):
        ст['роль_не_общая'] += 1
    if фри:
        ст['фримейл'] += 1
        if если_роль:
            ст['фримейл_с_ролью'] += 1
    if cr[:10] >= '2026-08-24':
        ст['новых_сегодня'] += 1
        if если_роль:
            ст['новых_с_ролью'] += 1
s.close()
print(json.dumps(ст, ensure_ascii=False, indent=1))
