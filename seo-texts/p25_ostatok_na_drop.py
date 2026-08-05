# -*- coding: utf-8 -*-
"""Выложить на дроп остаток карточек, который не прочла регулярка, — для провайдера.

Разбор карточек идёт НА СЕРВЕРЕ, а ключ провайдера лежит в песочнице. Значит текст надо
передать: сервер кладёт остаток на обменник, песочница забирает и читает провайдером.

Остаток измерен: из 9 335 карточек регулярка не разобрала 1 644, починка шаблона
телефона вернула 574, провайдеру осталось 1 070 карточек и 1,97 млн знаков.
"""
import json
import os
import urllib.request

VHOD = r'C:\sender\_ops\3s_karty_ostatok_provaydery.jsonl'
IMYA = 'P25-KARTY-OSTATOK-3S.jsonl'

if not os.path.exists(VHOD):
    print('ИТОГ ' + json.dumps({'ошибка': 'остатка нет, сперва прогнать замер щелей'},
                               ensure_ascii=False))
    raise SystemExit

dannye = open(VHOD, 'rb').read()
url, tok = os.environ.get('DROP_URL', ''), os.environ.get('DROP_TOKEN', '')
rq = urllib.request.Request(url.rstrip('/') + '/' + IMYA, data=dannye, method='PUT')
rq.add_header('X-Drop-Token', tok)
otvet = urllib.request.urlopen(rq, timeout=300).status

strok = sum(1 for _ in open(VHOD, encoding='utf-8'))
print('ИТОГ ' + json.dumps({'файл': IMYA, 'строк': strok, 'байт': len(dannye),
                            'ответ дропа': otvet}, ensure_ascii=False))
