# -*- coding: utf-8 -*-
"""Проверить привязку записей zakupki:eis по САМОЙ карточке. Резюмируемо.

Зачем. Архивный прогон показал, что `find_zakupki_contacts` не проверял
принадлежность вообще: из 24 проверенных строк 6 стояли на карточках ЧУЖИХ
заказчиков. Дешёвый признак «одна ссылка у нескольких ИНН» дал всего 41 строку
— но он ловит лишь раздачу одной карточки нескольким компаниям и слеп к
случаю, когда карточка приписана ровно одной, но НЕ ТОЙ компании. Значит
нижняя граница, а не ответ. Настоящий признак один: есть ли ИНН компании на
её карточке.

Рубеж ЗАКРЫТ ПО УМОЛЧАНИЮ ровно наоборот, чем обычно: здесь «не смог
проверить» — это НЕ приговор. Страница могла не открыться, и удалять по
такому поводу значит терять годное. Поэтому три исхода: ИНН найден (годно),
страница открылась и ИНН нет (порча), страница не открылась (неизвестно).

Ничего не удаляет — только размечает поток. Чистка отдельным прогоном, чтобы
решение принималось по цифрам, а не по ходу.
"""
import io
import json
import os
import re
import sys
import time
sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC
import enrich_db as EDB

ПОТОК = r'C:\seostat\drop\eis_attr_check.jsonl'
БЮДЖЕТ = float(sys.argv[1]) if len(sys.argv) > 1 else 300.0
НАЧАЛО = time.time()

db = EDB.EnrichDB()
e = db.cx
сделано = set()
if os.path.exists(ПОТОК):
    for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            d = json.loads(ln)
            сделано.add((d.get('инн'), d.get('ссылка')))
        except Exception:  # noqa: BLE001
            pass

пары = []
for табл in ('phone_contacts', 'emails'):
    for inn, url, шт in e.execute(
            f'SELECT inn, source_url, count(*) FROM {табл} '
            "WHERE lower(source) LIKE '%zakupki%' AND source_url LIKE 'http%' "
            'GROUP BY 1,2'):
        if (inn, url) not in сделано:
            пары.append({'инн': inn, 'ссылка': url, 'таблица': табл, 'строк': шт})
# одна пара может встречаться в обеих таблицах — качаем страницу один раз
уник = {}
for p in пары:
    уник.setdefault((p['инн'], p['ссылка']), {'инн': p['инн'], 'ссылка': p['ссылка'],
                                              'строк': 0})['строк'] += p['строк']
работа = list(уник.values())
print(json.dumps({'старт': True, 'уже_проверено': len(сделано),
                  'осталось_пар': len(работа)}, ensure_ascii=False))

ф = io.open(ПОТОК, 'a', encoding='utf-8')
св = {'проверено': 0, 'годно': 0, 'порча': 0, 'неизвестно': 0}
for p in работа:
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        break
    try:
        raw, ctype = EC._fetch_raw(p['ссылка']) if hasattr(EC, '_fetch_raw') \
            else (None, None)
    except Exception:  # noqa: BLE001
        raw, ctype = None, None
    txt = ''
    if raw is None:
        try:
            html, _m, _t = EC._fetch_site(p['ссылка'])
            txt = html or ''
        except Exception:  # noqa: BLE001
            txt = ''
    else:
        txt = EC._раскодировать(raw, ctype)
    if not txt or len(txt) < 3000:
        итог = 'неизвестно'
    else:
        плоско = re.sub(r'\D', '', txt)
        итог = 'годно' if p['инн'] in плоско else 'порча'
    св['проверено'] += 1
    св[итог] += 1
    ф.write(json.dumps({**p, 'вердикт': итог, 'байт': len(txt)},
                       ensure_ascii=False) + '\n')
    ф.flush()
    os.fsync(ф.fileno())
ф.close()
print(json.dumps({**св, 'поток': ПОТОК}, ensure_ascii=False))
