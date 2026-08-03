# -*- coding: utf-8 -*-
"""Только выдача: найти URL сайта и записать. Проверку делаем в песочнице.

Прежний прогон обрабатывал 74 цели из 589 за бюджет времени: на каждую цель уходил один запрос
в выдачу ПЛЮС девять скачиваний страниц ради поиска ИНН. Скачивание — самая дорогая часть, и она
занимает серверный воркер, который нужен всем трём сессиям.

Разделяю: сервер делает то, что умеет только он (ключ xmlriver), песочница — то, что дёшево ей
(качать страницы и сверять признаки). Журнал тот же по формату, поле `инн_на_странице` не
заполняется вовсе — его проставит проверка на моей стороне, честно и отдельным признаком.
"""
import json
import os
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

ЦЕЛИ = sys.argv[sys.argv.index('--targets') + 1]
ЖУРНАЛ = r'C:\sender\server\serp_only_3s.jsonl'
ЛИМ = int(sys.argv[sys.argv.index('--lim') + 1]) if '--lim' in sys.argv else 900
БЮДЖЕТ = int(sys.argv[sys.argv.index('--budget') + 1]) if '--budget' in sys.argv else 1050

опрошены = set()
if os.path.exists(ЖУРНАЛ):
    for ln in open(ЖУРНАЛ, encoding='utf-8'):
        try:
            опрошены.add(json.loads(ln).get('инн'))
        except Exception:  # noqa: BLE001
            pass
цели = []
for ln in open(ЦЕЛИ, encoding='utf-8'):
    try:
        c = json.loads(ln)
        if c['inn'] not in опрошены:
            цели.append(c)
    except Exception:  # noqa: BLE001
        pass
цели = цели[:ЛИМ]
print(f'уже опрошено ранее: {len(опрошены)}; на этот раз: {len(цели)}', flush=True)

начало = time.time()
нашли = пусто = ошибок = 0
for i, c in enumerate(цели, 1):
    if time.time() - начало > БЮДЖЕТ:
        print(f'бюджет времени вышел на {i} из {len(цели)}', flush=True)
        break
    имя = c.get('poln') or ''
    try:
        сайт, откуда, _ = EC.find_site_via_xmlriver({'name': имя, 'city': c.get('region') or ''})
    except Exception as e:  # noqa: BLE001
        ошибок += 1
        continue
    запись = {'инн': c['inn'], 'имя': имя[:80], 'сайт': сайт or '', 'откуда': откуда}
    with open(ЖУРНАЛ, 'a', encoding='utf-8') as ж:
        ж.write(json.dumps(запись, ensure_ascii=False) + '\n')
        ж.flush()
        os.fsync(ж.fileno())
    if сайт:
        нашли += 1
    else:
        пусто += 1
    if i % 50 == 0:
        print(f'  … {i}: с сайтом {нашли}, пусто {пусто}, ошибок {ошибок}, '
              f'{round(time.time()-начало)}с', flush=True)
print(f'ИТОГ: обработано {min(i, len(цели))}, сайт найден {нашли}, пусто {пусто}, '
      f'ошибок {ошибок}', flush=True)
