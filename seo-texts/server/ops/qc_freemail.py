# -*- coding: utf-8 -*-
"""Флаг «адрес на ПУБЛИЧНОМ бесплатном почтовом сервисе».

ЧТО ИМЕННО МЕРЯЕТ — и чего НЕ меряет. Признак вычисляется по ЛИТЕРАЛЬНОМУ
домену адреса (то, что после «@»), сверенному со списком публичных бесплатных
сервисов. Это НЕ «личный ящик сотрудника» и НЕ «мусор из реестра» — это лишь
«адрес заведён на бесплатном публичном сервисе, а не на домене компании».
Разница принципиальна: 29.07 в этом проекте уже подменили признак, разделив
компании по MX-хосту и назвав это «своя почта против публичного ящика» — а 681
из 684 «яндексовых» доменов оказались корпоративными (Яндекс 360 на своём
домене). Здесь MX не участвует ВООБЩЕ: смотрим только строку домена адреса.

Три класса адреса:
  свой      — домен адреса совпадает с доменом сайта компании (companies.site);
  публичный — домен адреса в списке бесплатных сервисов;
  прочий    — ни то ни другое (домен холдинга, старый домен, подрядчик).

Durable: колонка emails.addr_class (миграцией) + таблица email_class + поток.
Ничего не удаляет — только помечает.

Запуск: python qc_freemail.py [--apply]
"""
import io
import json
import os
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB      # noqa: E402
import enrich_contacts as EC  # noqa: E402

ПРИМЕНИТЬ = '--apply' in sys.argv
ПОТОК = r'C:\seostat\drop\qc_freemail_stream.jsonl'
print(json.dumps({'ГОЛОВА': 'qc_freemail старт', 'apply': ПРИМЕНИТЬ},
                 ensure_ascii=False))
sys.stdout.flush()

db = EDB.EnrichDB()
e = db.cx

# Публичные бесплатные почтовые сервисы. Список ЛИТЕРАЛЬНЫЙ: важно, что адрес
# заведён на чужом бесплатном сервисе, а не какой хостер держит MX.
ПУБЛИЧНЫЕ = {
    # Mail.ru Group
    'mail.ru', 'inbox.ru', 'list.ru', 'bk.ru', 'internet.ru', 'mail.ua',
    'xmail.ru', 'corp.mail.ru',
    # Яндекс
    'yandex.ru', 'yandex.com', 'yandex.by', 'yandex.kz', 'yandex.ua', 'ya.ru',
    'narod.ru', 'yandex.net',
    # Рамблер
    'rambler.ru', 'lenta.ru', 'autorambler.ru', 'myrambler.ru', 'ro.ru',
    'rambler.ua', 'r0.ru',
    # прочие рос./снг
    'qip.ru', 'pochta.ru', 'pochtamt.ru', 'front.ru', 'land.ru', 'nm.ru',
    'hotbox.ru', 'fromru.com', 'newmail.ru', 'smtp.ru', 'krovatka.su',
    'ukr.net', 'i.ua', 'meta.ua', 'bigmir.net', 'tut.by', 'bk.com',
    'mail.kz', 'inbox.lv', 'bigmir.net',
    # мировые
    'gmail.com', 'googlemail.com', 'yahoo.com', 'yahoo.co.uk', 'ymail.com',
    'outlook.com', 'outlook.ru', 'hotmail.com', 'hotmail.ru', 'live.com',
    'live.ru', 'msn.com', 'icloud.com', 'me.com', 'mac.com', 'aol.com',
    'proton.me', 'protonmail.com', 'protonmail.ch', 'tutanota.com',
    'tuta.io', 'zoho.com', 'gmx.com', 'gmx.net', 'gmx.de', 'mail.com',
    'web.de', 'fastmail.com', 'hushmail.com', 'yopmail.com',
    '163.com', '126.com', 'qq.com', 'sina.com', 'yeah.net', 'foxmail.com',
}

# домен сайта каждой компании
сайт_домен = {}
for inn, site in e.execute("select inn, site from companies where coalesce(site,'')<>''"):
    d = EC.site_domain(site)
    if d:
        сайт_домен[str(inn)] = d.lower()

e.execute("""CREATE TABLE IF NOT EXISTS email_class(
    inn TEXT, email TEXT, domain TEXT, addr_class TEXT, site_domain TEXT,
    updated_at TEXT, PRIMARY KEY(inn, email))""")
e.commit()
try:
    e.execute('ALTER TABLE emails ADD COLUMN addr_class TEXT')
    e.commit()
except Exception:  # noqa: BLE001
    pass


def класс(inn, dom):
    сд = сайт_домен.get(str(inn), '')
    if сд and (dom == сд or dom.endswith('.' + сд) or сд.endswith('.' + dom)):
        return 'свой'
    if dom in ПУБЛИЧНЫЕ:
        return 'публичный'
    return 'прочий'


строки = []
o = {'адресов': 0, 'классы': {}, 'классы_у_компаний_с_сайтом': {},
     'классы_у_компаний_без_сайта': {}}
for inn, em in e.execute("select inn, lower(trim(email)) from emails "
                         "where email like '%@%.%'"):
    if not em or em.count('@') != 1:
        continue
    dom = em.split('@')[1]
    k = класс(inn, dom)
    o['адресов'] += 1
    o['классы'][k] = o['классы'].get(k, 0) + 1
    есть_сайт = str(inn) in сайт_домен
    ключ = 'классы_у_компаний_с_сайтом' if есть_сайт else 'классы_у_компаний_без_сайта'
    o[ключ][k] = o[ключ].get(k, 0) + 1
    строки.append((str(inn), em, dom, k, сайт_домен.get(str(inn), ''), db.now))

if ПРИМЕНИТЬ:
    e.executemany('INSERT OR REPLACE INTO email_class'
                  '(inn,email,domain,addr_class,site_domain,updated_at)'
                  ' VALUES(?,?,?,?,?,?)', строки)
    e.execute('UPDATE emails SET addr_class=(SELECT c.addr_class FROM email_class c '
              'WHERE c.inn=emails.inn AND c.email=lower(trim(emails.email)))')
    e.commit()
    ф = io.open(ПОТОК, 'a', encoding='utf-8')
    ф.write(json.dumps({'ts': db.now, 'записано': len(строки)},
                       ensure_ascii=False) + '\n')
    ф.flush()
    os.fsync(ф.fileno())
    ф.close()

# ---- сколько компаний, у которых публичный адрес ЕДИНСТВЕННЫЙ ----
по_инн = {}
for inn, em, dom, k, сд, _ in строки:
    по_инн.setdefault(inn, []).append(k)
единств_публ = [i for i, ks in по_инн.items() if ks and all(x == 'публичный' for x in ks)]
o['компаний_с_почтой'] = len(по_инн)
o['компаний_только_публичные'] = len(единств_публ)
o['компаний_только_публичные_И_С_САЙТОМ'] = sum(
    1 for i in единств_публ if i in сайт_домен)
o['компаний_только_публичные_БЕЗ_САЙТА'] = sum(
    1 for i in единств_публ if i not in сайт_домен)
o['компаний_ровно_один_адрес_и_он_публичный'] = sum(
    1 for i, ks in по_инн.items() if len(ks) == 1 and ks[0] == 'публичный')
o['компаний_хоть_один_публичный'] = sum(
    1 for ks in по_инн.values() if 'публичный' in ks)
o['компаний_хоть_один_свой'] = sum(1 for ks in по_инн.values() if 'свой' in ks)
o['компаний_с_сайтом_в_companies'] = len(сайт_домен)

# топ публичных доменов
топ = {}
for inn, em, dom, k, сд, _ in строки:
    if k == 'публичный':
        топ[dom] = топ.get(dom, 0) + 1
o['топ_публичных_доменов'] = dict(sorted(топ.items(), key=lambda x: -x[1])[:15])

# сколько «публичных» адресов у компаний, у которых ЕСТЬ и свой корпоративный
o['публичных_адресов_у_компаний_где_есть_свой'] = sum(
    1 for i, ks in по_инн.items() if 'свой' in ks for k in ks if k == 'публичный')

print(json.dumps(o, ensure_ascii=False, indent=1))
print(json.dumps({'ХВОСТ': 'qc_freemail готов', 'адресов': o['адресов'],
                  'публичных': o['классы'].get('публичный'),
                  'только_публичные_компаний': o['компаний_только_публичные']},
                 ensure_ascii=False))
sys.stdout.flush()
os._exit(0)
