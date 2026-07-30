# -*- coding: utf-8 -*-
"""MX по доменам почт: сохранить ХОСТ, а не только флаг, и проверить гипотезу
«своя почта = крупная организация» на БОЛЬШОЙ выборке.

Откуда задача. В разборе engineers-lens MX предложили как бесплатный фильтр
сегмента: своя почта на своём домене — маркер крупной организации со своей
ИТ-службой (наш ICP), Яндекс/Mail.ru — маркер мелкой. Но вывод сделан по
10 доменам, и владелец 29.07 прямо сказал: «не факт что это точно, надо
проверять на большей выборке». Здесь и проверяем — на всех доменах базы,
сопоставляя с выручкой из companies.

Что делает:
  * тянет MX через nslookup (dnspython на сервере может не быть), кэширует в
    таблицу mx_domains — повторный прогон не ходит в DNS второй раз;
  * классифицирует держателя: своя / Яндекс / Mail.ru / Google / другой хостер;
  * считает медианную выручку и долю компаний по каждому классу — это и есть
    проверка гипотезы, а не пересказ.

Durable: таблица mx_domains в enrich.db + mx_scan.jsonl с fsync.
Запуск: python mx_scan.py [бюджет_сек] [потоков] [--recheck]
"""
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

_поз = [a for a in sys.argv[1:] if not a.startswith('--')]
БЮДЖЕТ = float(_поз[0]) if _поз else 600.0
ПОТОКОВ = int(_поз[1]) if len(_поз) > 1 else 12
ПЕРЕПРОВЕРКА = '--recheck' in sys.argv
НАЧАЛО = time.time()
ПОТОК = r'C:\seostat\drop\mx_scan.jsonl'

db = EDB.EnrichDB()
e = db.cx
e.execute("""CREATE TABLE IF NOT EXISTS mx_domains(
    domain TEXT PRIMARY KEY, mx_host TEXT, provider TEXT,
    n_mx INTEGER, checked_at TEXT)""")
e.commit()

# Кто держит почту. Порядок важен: сперва узнаваемые публичные сервисы,
# «своя» — это остаток, у которого MX на СВОЁМ домене (см. _класс).
_ПУБЛИЧНЫЕ = (
    ('Яндекс', ('mx.yandex.net', 'yandex.ru', 'yandex.net')),
    ('Mail.ru', ('mxs.mail.ru', 'mail.ru', 'bk.ru', 'list.ru', 'inbox.ru')),
    ('Google', ('google.com', 'googlemail.com', 'aspmx.l.google.com')),
    ('Microsoft', ('outlook.com', 'protection.outlook.com', 'office365.com')),
    ('Рег.ру', ('reg.ru',)),
    ('Timeweb', ('timeweb.ru', 'tmweb.ru')),
    ('Beget', ('beget.com', 'beget.ru')),
    ('Ростелеком/др. хостинг', ('hosting', 'masterhost', 'nic.ru', 'jino.ru')),
)


def _рег(домен):
    """Регистрируемая часть: последние две метки (для .co.uk неточно, нам не нужно)."""
    ч = (домен or '').strip('.').split('.')
    return '.'.join(ч[-2:]) if len(ч) >= 2 else домен


def _класс(домен, mx):
    mxl = (mx or '').lower()
    if not mxl:
        return 'нет MX'
    for имя, маркеры in _ПУБЛИЧНЫЕ:
        if any(m in mxl for m in маркеры):
            return имя
    # своя почта: MX лежит на том же регистрируемом домене (post.moren.ru у moren.ru)
    return 'своя' if _рег(mxl) == _рег(домен) else 'другой хостер'


def mx(домен):
    """MX-хосты домена по nslookup. Пусто — почты у домена нет/не ответил DNS."""
    try:
        r = subprocess.run(['nslookup', '-type=MX', домен], capture_output=True,
                           text=True, timeout=15, encoding='utf-8', errors='replace')
        txt = r.stdout or ''
    except Exception:  # noqa: BLE001
        return []
    хосты = re.findall(r'mail exchanger\s*=\s*(\S+)', txt, re.I)
    if not хосты:
        хосты = re.findall(r'MX preference\s*=\s*\d+,\s*mail exchanger\s*=\s*(\S+)',
                           txt, re.I)
    return [h.strip().rstrip('.') for h in хосты]


домены = [r[0] for r in e.execute(
    "select distinct lower(substr(email, instr(email,'@')+1)) as d "
    "from emails where email like '%@%' and coalesce(trim(email),'')<>'' "
    'order by d')]
готово = set() if ПЕРЕПРОВЕРКА else {
    r[0] for r in e.execute("select domain from mx_domains "
                            "where coalesce(checked_at,'')<>''")}
todo = [d for d in домены if d and d not in готово]

замок = threading.Lock()
ф = io.open(ПОТОК, 'a', encoding='utf-8')
out = {'доменов_всего': len(домены), 'в_очереди': len(todo), 'проверено': 0,
       'без_mx': 0}


def работа(домен):
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        return
    хосты = mx(домен)
    кл = _класс(домен, хосты[0] if хосты else '')
    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    with замок:
        e.execute('INSERT OR REPLACE INTO mx_domains'
                  '(domain,mx_host,provider,n_mx,checked_at) VALUES (?,?,?,?,?)',
                  (домен, хосты[0] if хосты else '', кл, len(хосты), ts))
        out['проверено'] += 1
        if not хосты:
            out['без_mx'] += 1
        if out['проверено'] % 25 == 0:
            e.commit()
        ф.write(json.dumps({'домен': домен, 'mx': хосты[:2], 'класс': кл},
                           ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())


with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
    list(пул.map(работа, todo))
e.commit()
ф.close()

# ---- ПРОВЕРКА ГИПОТЕЗЫ: связан ли держатель почты с размером компании ----
свод = {}
for пров, n, мед, дол in e.execute("""
    with dom as (
      select distinct lower(substr(em.email, instr(em.email,'@')+1)) d, em.inn
      from emails em where em.email like '%@%'),
    j as (
      select m.provider p, c.inn, cast(c.revenue_rub as real) v
      from dom join mx_domains m on m.domain = dom.d
      join companies c on c.inn = dom.inn)
    -- СЧИТАЕМ ПО КОМПАНИЯМ, А НЕ ПО СТРОКАМ. Раньше числитель был
    -- sum(case when v>=1e9), то есть считал СТРОКИ таблицы emails, а
    -- знаменатель count(distinct inn) — КОМПАНИИ. У компании адресов много,
    -- поэтому группа «своя почта» раздувалась с 572 до 788, а avg(v) был
    -- взвешен по числу адресов: у кого больше почт, тот сильнее тянул
    -- «среднюю выручку». Сперва схлопываем до одной строки на ИНН.
    , u as (select distinct p, inn, v from j)
    select p, count(*),
           avg(v),
           sum(case when v >= 1000000000 then 1 else 0 end)
    from u group by p order by 2 desc"""):
    свод[пров] = {'компаний': n,
                  'средняя_выручка_млн': round((мед or 0) / 1e6, 1),
                  'из_них_от_1_млрд': дол}
out['держатель_почты'] = свод
out['как_читать'] = ('гипотеза «своя почта = крупная компания» подтверждается, '
                     'если у класса «своя» средняя выручка и доля от 1 млрд '
                     'заметно выше, чем у Яндекс/Mail.ru')
print(json.dumps(out, ensure_ascii=False, indent=1))
sys.stdout.flush()
os._exit(0)
