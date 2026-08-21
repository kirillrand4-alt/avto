# -*- coding: utf-8 -*-
r"""Сверка выложенных модулей: sha, синтаксис и работает ли новая чистилка."""
import hashlib
import json
import sys

d = {}
for п in (r'C:\sender\sender\lid_ssylka.py', r'C:\sender\sender\lid_stranica.py',
          r'C:\sender\sender\api\app.py'):
    данные = open(п, 'rb').read()
    d.setdefault('sha', {})[п.split('\\')[-1]] = {
        'байт': len(данные),
        'sha': hashlib.sha256(данные).hexdigest()[:16]}
    try:
        compile(данные.decode('utf-8'), п, 'exec')
        d['sha'][п.split('\\')[-1]]['синтаксис'] = 'ок'
    except SyntaxError as e:  # noqa: BLE001
        d['sha'][п.split('\\')[-1]]['синтаксис'] = str(e)[:120]

sys.path.insert(0, r'C:\sender')
sys.path.insert(0, r'C:\sender\sender')
try:
    from sender import lid_ssylka as LS
except Exception:  # noqa: BLE001
    import lid_ssylka as LS
проба = (
    'Добрый день! Компрессор нам сейчас не нужен, спросите в январе.\n'
    'С уважением, Иван Петров, главный инженер, +7 900 000-00-00\n\n'
    'В пн, 18 авг 2026 в 10:00, Олег Цейзер <oleg@kompressor-air-exp.ru> писал(а):\n'
    '> Добрый день!\n'
    '> Смотрел производство...\n'
    '> С уважением,\n'
    '> Менеджер по продажам, Олег Цейзер\n'
    '> «Компрессор Центр»\n'
    '> ООО «Руспром», ИНН 2221239841\n')
чисто = LS.bez_citaty(проба)
d['проба_чистки'] = {
    'наша_подпись_ушла': 'Олег Цейзер' not in чисто,
    'подпись_клиента_на_месте': 'Иван Петров' in чисто,
    'телефон_клиента_на_месте': '+7 900 000-00-00' in чисто,
    'шапка_цитаты_ушла': 'писал(а)' not in чисто,
    'результат': чисто,
}
d['есть_bez_citaty'] = hasattr(LS, 'bez_citaty')
print(json.dumps(d, ensure_ascii=False, indent=1))
