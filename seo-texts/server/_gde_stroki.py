# -*- coding: utf-8 -*-
"""Есть ли ключевые строки карточки лида в живом и новом бандле."""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
СТРОКИ = ('ответ клиента', 'письмо не доставлено', 'Черновик ответа готов',
          'Компания: контакты и люди', 'Прикрепить файл', 'перевести')


def читать(корень):
    инд = os.path.join(корень, 'index.html')
    m = re.search(r'assets/(index-[\w-]+\.js)',
                  io.open(инд, encoding='utf-8', errors='replace').read())
    п = os.path.join(корень, 'assets', m.group(1))
    return m.group(1), io.open(п, encoding='utf-8', errors='replace').read()


из = {}
for имя, корень in (('живой', r'C:\sender\web\dist'),
                    ('новый', r'C:\sender\sender\web\dist')):
    файл, текст = читать(корень)
    из[имя] = {'бандл': файл, 'размер': len(текст),
               'строки': {с: (с in текст) for с in СТРОКИ}}
print(json.dumps(из, ensure_ascii=False, indent=1))
