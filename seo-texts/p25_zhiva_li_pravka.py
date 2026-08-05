# -*- coding: utf-8 -*-
"""Жива ли моя правка шаблона карточки. 1-я сессия выложила panel-update.zip — мог затереть.

Я в 09:00 починила centro_card.html: должность из position (было post, поля нет), и
строку про привязку. 1-я сессия в 06:54 выложила panel-update.zip + update-panel.ps1.
Если панель пересобирается из этого архива, моя правка могла быть затёрта. Проверяю
живой файл: стоит ли в нём p.position и строка про привязку, и есть ли ещё p.post.
Печатаю числами, ничего не меняю.
"""
import io
import json
import os
import re

SHABLON = r'C:\seostat\app\templates\centro_card.html'
itog = {}
if not os.path.exists(SHABLON):
    print('ИТОГ ' + json.dumps({'файла нет': True}, ensure_ascii=False))
    raise SystemExit
t = io.open(SHABLON, encoding='utf-8').read()
itog['p.position в шаблоне'] = t.count('p.position')
itog['p.post ещё остался'] = t.count('{{ p.post }}') + t.count('if p.post')
itog['строка про привязку'] = 'privyazka_somnitelna' in t
itog['проверена по строке источника'] = 'проверена по строке источника' in t
itog['mtime шаблона'] = int(os.path.getmtime(SHABLON))
# Резервные копии рядом — сколько и свежайшая.
kopii = [f for f in os.listdir(os.path.dirname(SHABLON)) if f.startswith('centro_card.html.bak')]
itog['резервных копий'] = len(kopii)
zhiva = itog['p.position в шаблоне'] >= 1 and itog['строка про привязку'] and \
    itog['p.post ещё остался'] == 0
itog['ПРАВКА ЖИВА'] = zhiva
for k, v in itog.items():
    print('REC %s\t%s' % (k, v))
print('ИТОГ ' + json.dumps(itog, ensure_ascii=False))
