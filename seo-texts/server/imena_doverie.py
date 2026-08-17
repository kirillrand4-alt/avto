# -*- coding: utf-8 -*-
r"""Единая таблица доверия к именам: кому можно писать по имени, а кому нельзя.

Владелец 17.08: «тогда не надо обращаться по фамилии, а вот все места где
подтверждено имя, сделай чтобы сессия поняла что этому можно верить».

Задача не в том, чтобы собрать имена — они уже собраны в двух местах (people и
emails). Задача в том, чтобы РЕШЕНИЕ было принято здесь и один раз, а не
пересобиралось каждой сессией по-своему. Панель сейчас считает имя надёжным по
формуле «contact_name + свой сайт + ссылка», и всё остальное молча выбрасывает —
включая 3037 ответственных по ОПО из реестра Ростехнадзора.

Четыре уровня, и различие между ними не в качестве данных, а в ПРАВЕ обратиться:

  сайт      имя и должность взяты со страницы самой компании, есть ссылка.
            Человек сам себя опубликовал как контакт — обращаться можно.
  реестр    Ростехнадзор (ответственный по ОПО), госзакупки, тендерные площадки.
            Человек реальный, должность известна, ссылка есть. НО контакт он не
            публиковал — его внесли в государственный список. Для нашего профиля
            это лучший собеседник (он отвечает за сосуды под давлением), однако
            приветствие по имени тут читается как «мы вас нашли в базе».
  егрюл     первое лицо из выписки. Верно юридически, но генеральный директор —
            редко тот, кто занимается закупкой компрессора.
  адрес     имя подтверждено только самим адресом (a.demchenko@momez.ru ->
            А. Демченко). Кроме фамилии и роли мы не знаем ничего: должности нет.
            Решение владельца 17.08 — по имени НЕ обращаться.

Итог кладём в таблицу imena в enrich.db: одна строка на человека, с уровнем,
доказательством и прямым флагом mozhno_po_imeni. Панели и соседним сессиям
достаточно прочитать флаг — разбираться в источниках им не нужно.

    python imena_doverie.py --stat       посчитать, ничего не записывая
    python imena_doverie.py --primenit   собрать таблицу imena
"""
import json
import os
import sqlite3
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import karantin_kesha as KK       # noqa: E402  (мерка «почти тот же домен»)
import ploshchadki as PL          # noqa: E402

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
СХЕМА = """CREATE TABLE IF NOT EXISTS imena(
    inn TEXT, person TEXT, post TEXT, role TEXT, email TEXT,
    uroven TEXT,            -- сайт | реестр | егрюл | адрес
    mozhno_po_imeni INTEGER,-- 1 = можно здороваться по имени
    dokazatelstvo TEXT,     -- ссылка или «адрес подтверждает имя»
    istochnik TEXT, ts TEXT,
    PRIMARY KEY(inn, person, email))"""
РЕЕСТРЫ = (('gosnadzor.ru', 'Ростехнадзор'), ('zakupki.gov.ru', 'госзакупки'),
           ('torgi.gov.ru', 'госзакупки'), ('tender.pro', 'тендерная площадка'),
           ('rts-tender', 'тендерная площадка'), ('b2b-center', 'тендерная площадка'))


def _свой(дом, сайт):
    if not дом or not сайт:
        return False
    return (дом == сайт or дом.endswith('.' + сайт) or сайт.endswith('.' + дом)
            or KK._почти_тот_же(дом, сайт))


def собрать():
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    сайты = {str(r[0]): PL.домен(r[1] or '') for r in c.execute(
        "select inn, coalesce(nullif(site,''),nullif(cand_site,''),'') from companies")}
    почтовые = {}
    for r in c.execute("select inn, email from emails where coalesce(email,'')<>''"):
        почтовые.setdefault(str(r['inn']), set()).add((r['email'].split('@')[-1] or '').lower())
    строки = []
    for r in c.execute("select inn, person, coalesce(post,'') post, coalesce(role,'') role, "
                       "coalesce(email,'') email, coalesce(source,'') ист, "
                       "coalesce(source_url,'') url from people "
                       "where coalesce(person,'')<>''"):
        inn = str(r['inn'])
        дом = PL.домен(r['url'])
        сайт = сайты.get(inn, '')
        if _свой(дом, сайт) or (дом and дом in (почтовые.get(inn) or set())):
            уровень, можно = 'сайт', 1
        elif 'nalog.ru' in дом or 'egrul' in r['url']:
            уровень, можно = 'егрюл', 0
        else:
            имя_реестра = next((n for k, n in РЕЕСТРЫ if k in дом), '')
            if имя_реестра:
                уровень, можно = 'реестр', 0
            elif дом:
                уровень, можно = 'реестр', 0      # чужая страница, но со ссылкой
            else:
                continue                           # без доказательства не берём
        строки.append({'inn': inn, 'person': r['person'][:120], 'post': r['post'][:120],
                       'role': r['role'][:60], 'email': r['email'][:120],
                       'uroven': уровень, 'mozhno': можно,
                       'dokazatelstvo': r['url'][:300], 'istochnik': r['ист'][:60]})
    # имена, подтверждённые самим адресом: должности нет, здороваться нельзя
    for r in c.execute("select inn, email, person, coalesce(role,'') role, "
                       "coalesce(source_url,'') url from emails where imya_ok=1 "
                       "and coalesce(person,'')<>''"):
        строки.append({'inn': str(r['inn']), 'person': r['person'][:120], 'post': '',
                       'role': r['role'][:60], 'email': r['email'][:120],
                       'uroven': 'адрес', 'mozhno': 0,
                       'dokazatelstvo': r['url'][:300] or 'адрес подтверждает имя',
                       'istochnik': 'imya_ok'})
    c.close()
    return строки


def применить():
    строки = собрать()
    c = sqlite3.connect(BD, timeout=60)
    c.execute(СХЕМА)
    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    n = 0
    for s in строки:
        c.execute("INSERT OR REPLACE INTO imena(inn, person, post, role, email, uroven, "
                  "mozhno_po_imeni, dokazatelstvo, istochnik, ts) "
                  'VALUES(?,?,?,?,?,?,?,?,?,?)',
                  (s['inn'], s['person'], s['post'], s['role'], s['email'], s['uroven'],
                   s['mozhno'], s['dokazatelstvo'], s['istochnik'], ts))
        n += 1
    c.commit()
    c.close()
    return {'записано': n, **свод(строки)}


def свод(строки=None):
    строки = собрать() if строки is None else строки
    по_уровням, компаний = {}, {}
    for s in строки:
        по_уровням[s['uroven']] = по_уровням.get(s['uroven'], 0) + 1
        компаний.setdefault(s['uroven'], set()).add(s['inn'])
    можно = [s for s in строки if s['mozhno']]
    return {'всего_имён': len(строки),
            'по_уровням': {k: {'записей': v, 'компаний': len(компаний[k])}
                           for k, v in sorted(по_уровням.items(), key=lambda x: -x[1])},
            'можно_по_имени': len(можно),
            'компаний_можно_по_имени': len({s['inn'] for s in можно})}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    if a and a[0] == '--primenit':
        print(json.dumps(применить(), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(свод(), ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
