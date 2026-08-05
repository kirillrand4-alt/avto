# -*- coding: utf-8 -*-
"""Показать СЫРЫЕ снимки выдачи по ЭкоНиве. Смотреть глазами, а не верить счётчику.

Поиск ЛПР дал одного человека, и тот ложный: ректор БелГАУ из PDF-отчёта вуза, где
«ЭкоНива-АПК» просто упомянута. 70 документов ушли в «без имён». Прежде чем сказать
«не нашлось», надо посмотреть, ЧТО в этих документах: страницы без людей — или мой
разбор не увидел людей, которые там есть.

Печатаю сырой текст снимков целиком. Никаких выводов — показ.
"""
import importlib.util
import json
import os
import re

KANDIDATY = [r'C:\sender\_ops\3s_lpr_obratnyy.py', r'C:\sender\server\lpr_obratnyy.py']
ZAPROSY = ['site:ekoniva-apk.ru руководство',
           'site:ekoniva-apk.ru контакты отдел',
           'site:ekoniva-apk.ru "главный энергетик"',
           'ЭкоНива "главный инженер"']

serp = None
for p in KANDIDATY:
    if os.path.exists(p):
        sp = importlib.util.spec_from_file_location('s', p)
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        serp = m.serp
        break
if not serp:
    print('ИТОГ ' + json.dumps({'поиска нет': True}, ensure_ascii=False))
    raise SystemExit

vsego = 0
for z in ZAPROSY:
    try:
        docs, err = serp(z)
    except Exception as e:  # noqa: BLE001
        print('\n### %s -> упал %s' % (z, e))
        continue
    docs = docs or []
    print('\n\n########## %s   документов %d' % (z, len(docs)))
    for i, d in enumerate(docs[:6], 1):
        url = d.get('url') or ''
        t = re.sub(r'\s+', ' ', str(d.get('tekst') or '')).strip()
        vsego += 1
        print('\n  --- %d. %s' % (i, url[:110]))
        print('      ключи документа: %s' % ', '.join(sorted(d.keys())))
        print('      текст (%d знаков): %s' % (len(t), t[:600] or '(ПУСТО)'))
print('\nИТОГ ' + json.dumps({'показано документов': vsego}, ensure_ascii=False))
